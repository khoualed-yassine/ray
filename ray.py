#!/usr/bin/env python

import sys, os, argparse

from numpy import unique
from imio import read_image_stack, write_h5_stack
from agglo import Rag
from morpho import watershed
from progressbar import ProgressBar, Percentage, Bar, ETA, RotatingMarker

def read_image_stack_single_arg(fn):
    """Read an image stack and print exceptions as they occur.
    
    argparse.ArgumentParser() subsumes exceptions when they occur in the 
    argument type, masking lower-level errors. This function prints out the
    error before propagating it up the stack.
    """
    try:
        return read_image_stack(fn)
    except Exception as err:
        print err
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Segment a volume using a superpixel-to-RAG model.'
    )
    parser.add_argument('fin', nargs='+', 
        help='The boundary probability map file(s).'
    )
    parser.add_argument('fout', 
        help='The output filename for the segmentation. Use %%str syntax.'
    )
    parser.add_argument('-I', '--invert-image', action='store_true',
        default=False,
        help='Invert the probabilities before segmenting.'
    )
    parser.add_argument('-w', '--watershed', metavar='WS_FN',
        type=read_image_stack_single_arg,
        help='Use a precomputed watershed volume from file.'
    )
    parser.add_argument('-t', '--thresholds', nargs='+', default=[128],
        type=float, metavar='FLOAT',
        help='''The agglomeration thresholds. One output file will be written
            for each threshold.'''
    )
    parser.add_argument('-l', '--ladder', type=int, metavar='SIZE',
        help='Merge any bodies smaller than SIZE.'
    )
    parser.add_argument('-p', '--pre-ladder', action='store_true', default=True,
        help='Run ladder before normal agglomeration (default).'
    )
    parser.add_argument('-L', '--post-ladder', 
        action='store_false', dest='pre_ladder',
        help='Run ladder after normal agglomeration instead of before (SLOW).'
    )
    parser.add_argument('-P', '--show-progress', action='store_true',
        default=True, help='Show a progress bar for the agglomeration.'
    )
    parser.add_argument('-S', '--save-watershed', metavar='FILE',
        help='Write the watershed result to FILE (overwrites).'
    )
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
        help='Print runtime information about execution.'
    )
    args = parser.parse_args()

    probs = read_image_stack(*args.fin)
    if args.invert_image:
        probs = probs.max() - probs
    if args.watershed is None:
        if args.verbose:
            print 'Computing watershed...'
        args.watershed = watershed(probs)
    if args.verbose:
        print 'Number of watershed basins: ',len(unique(args.watershed))-1
    if args.save_watershed is not None:
        # h5py sometimes has issues overwriting files, so delete ahead of time
        if os.access(args.save_watershed, os.F_OK):
            os.remove(args.save_watershed)
        write_h5_stack(args.watershed, args.save_watershed)

    if args.verbose:
        print 'Computing RAG for ws and image sizes:', args.watershed.shape,\
            probs.shape

    g = Rag(args.watershed, probs)

    if args.verbose:
        print 'RAG computed. Number of nodes: ', g.number_of_nodes(), \
            '. Number of edges: ', g.number_of_edges()

    if args.ladder is not None:
        if args.pre_ladder:
            if args.verbose:
                print 'Computing ladder agglomeration...'
            args.post_ladder = False
            g.agglomerate_ladder(args.ladder)
            g.rebuild_merge_queue()
            if args.verbose:
                print 'Ladder done. new graph statistics: n: ', \
                            g.number_of_nodes(), 'm: ', g.number_of_edges()
        else:
            args.post_ladder = True
    if args.show_progress:
        pbarwidgets = ['Agglomerating: ', RotatingMarker(), ' ',
                            Percentage(), ' ', Bar(marker='='), ' ', ETA()]
    else:
        pbarwidgets = []
    pbar = ProgressBar(widgets=pbarwidgets, maxval=len(args.thresholds))
    pbar.start()
    for i, t in enumerate(args.thresholds):
        g.agglomerate(t)
        if args.ladder is not None and args.post_ladder:
            g2 = g.copy()
            g2.agglomerate_ladder(args.ladder)
        else:
            g2 = g
        v = g2.build_volume()
        write_h5_stack(v, args.fout % t)
        pbar.update(i+1)
    pbar.finish()
