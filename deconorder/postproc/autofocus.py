import numpy as np
from scipy.ndimage import sobel
from cv2 import filter2D
from skimage.morphology import cube, disk
from skimage.filters import median


def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev) ** 2)


def quad(x, a, b, c):
    return a * x ** 2 + b * x + c


def tenengrad(img):
    M, N = img.shape
    sob1 = sobel(img, 0, mode='reflect')
    sob2 = sobel(img, 1, mode='reflect')

    Ten = np.sum(sob1 ** 2 + sob2 ** 2)

    return Ten


def vol4(img):
    img_adj = img.astype('int64')
    M, N = img.shape

    f1 = 0
    f2 = 0
    for x in range(M - 1):

        f1 += np.sum(img_adj[x, :] * img_adj[x + 1, :])

        if x < M - 2:
            f2 += np.sum(img_adj[x, :] * img_adj[x + 2, :])

    return f1 - f2


def brenner(img):
    img = img.astype('int64')
    M, N = img.shape

    score = 0
    for x in range(M - 2):
        score += np.sum((img[x, :] - img[x + 2, :]) ** 2)

    return score


def vol5(img):
    img_adj = img.astype('int64')
    M, N = img.shape
    mean = np.mean(img_adj)

    f1 = 0
    for x in range(M - 1):
        f1 += np.sum(img_adj[x, :] * img_adj[x + 1, :])

    return f1 - M * N * (mean ** 2)


def MDCT(img):
    M, N = img.shape

    op = np.array([[1, 1, -1, -1],
                   [1, 1, -1, -1],
                   [-1, -1, 1, 1],
                   [-1, -1, 1, 1]], dtype='float')

    conv = filter2D(img, -1, op)
    score = np.sum(conv ** 2)

    return score


def variance(img):
    return np.var(img)


def norm_variance(img):
    return np.var(img) / np.mean(img)


def conv_mm(img):
    op = np.array([[-2, 1, 0],
                   [-1, 0, -1],
                   [0, 1, 2]], dtype='float')

    img = median(img, disk(3))
    img = filter2D(img, -1, op)

    return np.sum(img ** 2)