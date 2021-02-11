import numpy as np
from colorspacious import cspace_convert
import matplotlib.pyplot as plt
import cv2
from .Image_Utils import nanRobustBlur, imadjust, im_bit_convert, imClip, imcrop


def aniso2hsv(s0, retardance, orientation, polarization, norm=True):
    """ Generate colormaps with following mappings, where H is Hue, S is Saturation, and V is Value.
        I_azi_ret_trans: H=Orientation, S=retardance, V=Brightfield.
        I_azi_ret: H=Orientation, V=Retardance.
        I_azi_pol: H=Orientation, V=Polarization.
    """

    if norm:
        retardance = imadjust(retardance, tol=1, bit=8)
        s0 = imadjust(s0, tol=1, bit=8)
        polarization = imadjust(polarization, tol=1, bit=8)
        # retardance = cv2.convertScaleAbs(retardance, alpha=(2**8-1)/np.max(retardance))
        # s0 = cv2.convertScaleAbs(s0, alpha=(2**8-1)/np.max(s0))
    else:
        #TODO: make scaling factors parameters in the config
        retardance = cv2.convertScaleAbs(retardance, alpha=50)
        s0 = cv2.convertScaleAbs(s0, alpha=100)
        polarization = cv2.convertScaleAbs(polarization, alpha=2000)
#    retardance = histequal(retardance)

    orientation = cv2.convertScaleAbs(orientation, alpha=1)
#    retardAzi = np.stack([orientation, retardance, np.ones(retardance.shape).astype(np.uint8)*255],axis=2)
    I_azi_ret_trans = np.stack([orientation, retardance, s0], axis=2)
    I_azi_ret = np.stack([orientation, np.ones(retardance.shape).astype(np.uint8) * 255, retardance], axis=2)
    I_azi_scat = np.stack([orientation, np.ones(retardance.shape).astype(np.uint8) * 255, polarization], axis=2)
    I_azi_ret_trans = cv2.cvtColor(I_azi_ret_trans, cv2.COLOR_HSV2RGB)
    I_azi_ret = cv2.cvtColor(I_azi_ret, cv2.COLOR_HSV2RGB)
    I_azi_scat = cv2.cvtColor(I_azi_scat, cv2.COLOR_HSV2RGB)  #
#    retardAzi = np.stack([orientation, retardance],axis=2)
    return I_azi_ret_trans, I_azi_ret, I_azi_scat

def overlay_retardance_orientation(retardance, orientation, ret_scale=(0, 1), method='JCH', ret_noise_level=0.5, 
                   ori_scale=(0, 180), ori_levels=8):
    
    J_max = 65
    C_max = 60
    ret_ = np.interp(retardance, ret_scale, (0, J_max))
    ori_binned = np.round(orientation/ori_scale[1] * ori_levels + 0.5)/ori_levels - 1/ori_levels
    ori_ = np.interp(ori_binned, (ori_scale[0]/ori_scale[1], 1), (0, 360)) 
    
    if method == 'JCH':
        
        J = ret_
        J[ret_<ret_noise_level] = 0
        C = np.ones_like(J) * C_max
#         C[retardance < ret_noise_level] = 0
        h = ori_

        JCh = np.stack((J, C, h), axis=-1)
        
        image = cspace_convert(JCh, "JCh", "sRGB255")
        
        image[image<0] = 0
        image[image>255] = 255

        return image.astype(np.uint8)
    
        
    if method == 'RGB':
        
        H = cv2.convertScaleAbs(ori_, alpha=1)
        S = np.ones(ret_.shape, dtype=np.uint8) * 255
        V = imadjust(ret_, tol=1, bit=8)
        V[retardance < ret_noise_level] = 0

        HSV = np.stack((H, S, V), axis=2)
        image = cv2.cvtColor(HSV, cv2.COLOR_HSV2RGB)
            
    return image

        

def create_legend(method='JCH',levels=8):
    
    [xLeg, yLeg] = np.meshgrid(np.arange(-1, 1+0.001, 0.001), np.arange(-1, 0.001, 0.001))
    rhoLeg = np.sqrt(xLeg**2 + yLeg**2)
    thetaLeg = np.arctan2(-yLeg, xLeg)

    # print(thetaLeg)
    # thetaLeg 
    thetaLeg %= np.pi
    # thetaLeg -= np.pi/2
    thetaLeg /= np.pi

    alpha = np.ones_like(rhoLeg)
    alpha[rhoLeg>=1] = 0
    alpha[rhoLeg<np.sqrt(1/3)] = 0

    levels = 8

    thetaLeg_ = np.round(thetaLeg*levels+0.5)/levels - 1/levels

    if method == 'JCH':
        J = np.ones_like(rhoLeg) * 45
        C = np.ones_like(rhoLeg) * 60
        h = thetaLeg_*360

        JCh = np.stack((J, C, h), axis=2)
        JCh_rgb = cspace_convert(JCh, "JCh", "sRGB1")

        JCh_rgb[JCh_rgb<0]=0
        JCh_rgb[JCh_rgb>1]=1

        legend = np.dstack((JCh_rgb, alpha))
        
    if method == 'RGB':
        
        H = np.ones_like(rhoLeg) * 45
        S = np.ones_like(rhoLeg) * 60
        V = thetaLeg_*360
        
        HSV = np.stack((H, S, V), axis=2)
        image = cv2.cvtColor(HSV, cv2.COLOR_HSV2RGB)
        
    plt.imshow(legend)
    plt.axis('off')
    
    
    return legend
