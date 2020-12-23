import imagej
import pywt
import numpy as np
import os
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
from .autofocus import tenengrad, vol5, vol4, variance, norm_variance, MDCT, brenner

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

    try:
        ij = imagej.init(path_to_fiji)
    except:
        raise ImportError("Make sure a local installation of Fiji + MIST is installed")

    ij.py.run_plugin('MIST', args=args)

#TODO: Make compatible Physical data data structure
def write_timeseries_video(data: PhysicalData, out_directory, filename, ffmpeg_path, fps, time_step, time_units='min', font_size = 8):
    """

    :param data: (object) Physical Data Object
    :param out_directory: (str) output directory where video will be saved
    :param filename: (str) filename of the video
    :param ffmpeg_path: (str) path to ffmpeg.  Needed to write .mp4 files.

    Ex: 'C:/Desktop/ffmpeg-4.3.1-win64-static/bin/ffmpeg.exe'
    Download from https://ffmpeg.org/download.html

    :param fps: (int) desired frame rate of the video.  Length of video will be fps * (# of frames)
    :param time_step: (float) Recorded time step between every frame
    :param time_units: (str) Units of the time step
    :param font_size: (int) default = 8

    :return: None
    """

    #TODO: make compatible with data structure
    time_data = data.get_image_data('TYX', S = 0, C = 0, Z=0)

    frame, height, width = np.shape(time_data)
    time = np.arange(0, frame, time_step)

    name = os.path.join(out_directory, filename)

    img1 = frame[0]

    fig, ax = plt.subplots(nrows=1, ncols=1, dpi=300)
    im1 = ax.imshow(img1, cmap='gray')
    txt = ax.text(0.98, 0.02, f'Time = {time[0]:5f} {time_units}', fontsize=font_size, fontweight='bold', color='w',
                  horizontalalignment='right', transform=ax.transAxes)
    ax.get_xaxis().set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.tight_layout()

    def init():
        return im1, txt

    def animate(i):
        im1.set_data(frame[i])
        txt.set_text(f'Time = {time[0]:5f} {time_units}')
        return im1, txt

    ani = FuncAnimation(fig, animate, frames=len(frame),
                        init_func=init, blit=True)

    plt.rcParams['animation.ffmpeg_path'] = ffmpeg_path
    writer = FFMpegWriter(fps=fps, extra_args=['-vcodec', 'libx264'])

    ani.save(name+'.mp4', writer=writer)

#TODO: Make compatible with image reader for either Stokes or Intensity data
def wavelet_softThreshold(img, wavelet, threshold, level=1, axes=None):
    '''
    soft thresholding in the nD wavelet space
    Input:
        img       : ndarray, image or volume in nD space
        wavelet   : str,     type of wavelet to use (pywt.wavelist() to find the whole list)
        threshold : float,   threshold value
    Output:
        img_thres : ndarray, denoised image or volume in nD space
    '''

    coeffs = pywt.wavedecn(img, wavelet, level=level, axes=axes)

    for i in range(level + 1):
        if i == 0:
            coeffs[i] = softTreshold(coeffs[i], threshold)
        else:
            for item in coeffs[i]:
                coeffs[i][item] = softTreshold(coeffs[i][item], threshold)

    img_thres = pywt.waverecn(coeffs, wavelet, axes=axes)

    return img_thres


def find_focus_slice(data: PhysicalData, position, method = 'Brenner', plot=True):
    """ This function will take physical data and run through a z-stack to evaluate the "focus score"
    at every z-index.  The maximum calculated score will be the focused z-slice.  Does not work with
    Brightfield Images

    :param data: Physical Data Object
    :param position: Position index to evaluate focus
    :param method: Autofocus Figure of Merit function to maximize

        'Brenner': Fast Edge-finding method (preferred)
        'Variance': statistical variance
        'Norm Variance': normalized statistical variance
        'Tenengrad': gradient magnitude maximization based on Sobel operators
        'MDCT': Modified Discrete Cosine Transform
        'Vol4': Volath's F4
        'Vol5': Volath's F5

    :param plot: (bool) whether to plot the scores as a function of z-index
    :return: (int) the focused z-slice index
    """

    #TODO: Change to be compatible with the physical data structure, not created yet
    stack = data.get_image_data('ZYX', S=position, T=0, C=0)

    score = []
    for z in range(len(stack)):

        if method == 'Brenner':
            score.append(brenner(stack[z]))

        elif method == 'Tenengrad':
            score.append(tenengrad(stack[z]))

        elif method == 'Variance':
            score.append(variance(stack[z]))

        elif method == 'Norm Variance':
            score.append(norm_variance(stack[z]))

        elif method == 'MDCT':
            score.append(MDCT(stack[z]))

        elif method == 'Vol5':
            score.append(vol5(stack[z]))

        elif method == 'Vol4':
            score.append(vol4(stack[z]))

        else:
            raise ValueError('Method not found')

        focus_idx = np.where(score1 == np.max(score1))[0]

        if plot:
            plt.figure(fig_size=(7,1))
            plt.title(f'{method} Autofocus Assessment')
            plt.plot(score)
            plt.xlabel('Z-Index')
            plt.ylabel('Score')
            plt.axvline(focus_idx, color='r', lw='0.1')
            plt.text(focus_idx, 1, f'Z={focus_idx}')

        print(f'The focused z-slice index for Position {position} is {focus_idx}')

        return focus_idx


