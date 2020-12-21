import imagej

def stitch_MIST(path_to_fiji,
                img_dir, filename_pattern, output_dir,  output_filename,
                grid_width, grid_height, grid_origin, horiz_overlap, vert_overlap, overlap_uncertainty,
                start_row = 0, start_column = 0, width, height,
                blend_mode = 'LINEAR',
                output_img_pyramid = False):

    args = {"gridwidth": grid_width,"gridheight": grid_height,
                     "starttile":0,
                     "imagedir": img_dir,
                     "filenamepattern": filename_pattern,
                     "filenamepatterntype": "SEQUENTIAL",
                     "gridorigin": grid_origin,
                     "assemblefrommetadata": "false",
                   "assemblenooverlap":"false",
                   "globalpositionsfile": "",
                   "numberingpattern":"HORIZONTALCONTINUOUS",
                   "startrow": start_row, "startcol": start_column, "extentwidth": width, "extentheight": height,
                   "timeslices": 0, "istimeslicesenabled": "false",
                   "outputpath": output_dir,
                   "displaystitching": "false",
                   "outputfullimage": "true",
                   "outputmeta": "true",
                   "outputimgpyramid": output_img_pyramid,
                   "blendingmode": blend_mode,
                   "blendingalpha": "NaN",
                   "outfileprefix": output_filename,
                   "programtype": "AUTO",
                   "numcputhreads": 16,
                   "loadfftwplan": "true",
                   "savefftwplan": "true",
                   "fftwplantype": "MEASURE",
                   "fftwlibraryname": "libfftw3",
                   "fftwlibraryfilename": "libfftw3.dll",
                   "planpath": "/home/camfoltz2/Downloads/Fiji.app/lib/fftw/fftPlans",
                   "fftwlibrarypath": "/home/camfoltz2/Downloads/Fiji.app/lib/fftw",
                   "stagerepeatability": 0,
                   "horizontaloverlap": horiz_overlap,
                   "verticaloverlap": vert_overlap,
                   "numfftpeaks": 0,
                   "overlapuncertainty": overlap_uncertainty,
                   "isusedoubleprecision": "false",
                   "isusebioformats": "false",
                   "issuppressmodelwarningdialog": "false",
                   "isenablecudaexceptions": "false",
                   "translationrefinementmethod": "SINGLE_HILL_CLIMB",
                   "numtranslationrefinementstartpoints": 16,
                   "headless": "true",
                   "loglevel": "MANDATORY",
                   "debuglevel": "NONE"
                  }

    ij = imagej.init(path_to_fiji)
    ij.py.run_plugin('MIST', args=args)


def write_video():
    pass

def denoise():
