# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/API/co.ipynb.

# %% auto 0
__all__ = ['emperical_co', 'nearestPD', 'regularize_spectral']

# %% ../nbs/API/co.ipynb 5
import cupy as cp
from typing import Union

# %% ../nbs/API/co.ipynb 7
_emperical_co_kernel = cp.ElementwiseKernel(
    'raw T rslc, raw bool is_shp, int32 nlines, int32 width, int32 nimages, int32 az_half_win, int32 r_half_win',
    'raw T cov, raw T coh',
    '''
    if (i >= nlines*width) return;
    int az_win = 2*az_half_win+1;
    int r_win = 2*r_half_win+1;
    int win = az_win*r_win;
    
    int ref_az = i/width;
    int ref_r = i -ref_az*width;

    int sec_az, sec_r;

    int m,j; // index of each coherence matrix
    int k,l; // index of search window
    T _cov; // covariance
    float _amp2_m; // sum of amplitude square for image i
    float _amp2_j; // sum of amplitude aquare for image j
    int rslc_inx_m, rslc_inx_j;
    int n; // number of shp

    for (m = 0; m < nimages; m++) {
        for (j = 0; j < nimages; j++) {
            _cov = T(0.0, 0.0);
            _amp2_m = 0.0;
            _amp2_j = 0.0;
            n = 0;
            for (k = 0; k < az_win; k++) {
                for (l = 0; l < r_win; l++) {
                    sec_az = ref_az-az_half_win+k;
                    sec_r = ref_r-r_half_win+l;
                    if (is_shp[i*win+k*r_win+l] && sec_az >= 0 && sec_az < nlines && sec_r >= 0 && sec_r < width) {
                        rslc_inx_m = (sec_az*width+sec_r)*nimages+m;
                        rslc_inx_j = (sec_az*width+sec_r)*nimages+j;
                        _amp2_m += norm(rslc[rslc_inx_m]);
                        _amp2_j += norm(rslc[rslc_inx_j]);
                        _cov += rslc[rslc_inx_m]*conj(rslc[rslc_inx_j]);
                        n += 1;
                        //if (i == 0 && m ==3 && j == 1) {
                        //    printf("%f",_cov.real());
                        //}
                    }
                }
            }
            cov[(i*nimages+m)*nimages+j] = _cov/(float)n;
            //if ( i == 0 && m==3 && j ==1 ) printf("%d",((i*nimages+m)*nimages+j));
            _amp2_m = sqrt(_amp2_m*_amp2_j);
            coh[(i*nimages+m)*nimages+j] = _cov/_amp2_m;
        }
    }
    ''',
    name = 'emperical_co_kernel',reduce_dims = False,no_return=True
)

# %% ../nbs/API/co.ipynb 8
def emperical_co(rslc:cp.ndarray, # rslc stack, dtype: `cupy.complexfloating`
            is_shp:cp.ndarray, # shp bool, dtype: `cupy.bool`
            block_size:int=128, # the CUDA block size, it only affects the calculation speed
            )-> tuple[cp.ndarray,cp.ndarray]: # the covariance and coherence matrix `cov` and `coh`
    '''
    Maximum likelihood covariance estimator.
    '''
    nlines, width, nimages = rslc.shape
    az_win, r_win = is_shp.shape[-2:]
    az_half_win = (az_win-1)//2
    r_half_win = (r_win-1)//2

    cov = cp.zeros((nlines,width,nimages,nimages),dtype=rslc.dtype)
    coh = cp.empty((nlines,width,nimages,nimages),dtype=rslc.dtype)

    _emperical_co_kernel(rslc, is_shp, cp.int32(nlines),cp.int32(width),cp.int32(nimages),
                    cp.int32(az_half_win),cp.int32(r_half_win),cov,coh,size = nlines*width,block_size=block_size)
    return cov,coh

# %% ../nbs/API/co.ipynb 21
def _isPD(co:cp.ndarray, # absolute value of complex coherence/covariance stack
         )-> cp.ndarray: # bool array indicating wheather coherence/covariance is positive define
    L = cp.linalg.cholesky(co)
    isPD = cp.isfinite(L).all(axis=(-2,-1))
    return isPD

# %% ../nbs/API/co.ipynb 22
'''
    The method is presented in [1]. John D'Errico implented it in MATLAB [2] under BSD
    Licence and [3] implented it with Python/Numpy based on [2] also under BSD Licence.
    This is a cupy implentation with stack of matrix supported.

    [1] N.J. Higham, "Computing a nearest symmetric positive semidefinite
    matrix" (1988): https://doi.org/10.1016/0024-3795(88)90223-6
    
    [2] https://www.mathworks.com/matlabcentral/fileexchange/42885-nearestspd
    
    [3] https://gist.github.com/fasiha/fdb5cec2054e6f1c6ae35476045a0bbd
'''
def nearestPD(co:cp.ndarray, # stack of matrix with shape [...,N,N]
             )-> cp.ndarray: # nearest positive definite matrix of input, shape [...,N,N]
    """Find the nearest positive-definite matrix to input matrix."""

    B = (co + cp.swapaxes(co,-1,-2))/2
    s, V = cp.linalg.svd(co)[1:]
    I = cp.eye(co.shape[-1],dtype=co.dtype)
    S = s[...,None]*I
    
    H = np.matmul(cp.swapaxes(V,-1,-2), np.matmul(S, V))
    A2 = (B + H) / 2
    A3 = (A2 + cp.swapaxes(A2,-1,-2))/2

    if _isPD(A3).all():
        return A3
    
    co_norm = cp.linalg.norm(co,axis=(-2,-1))
    spacing = cp.nextafter(co_norm,co_norm+1.0)-co_norm
    
    k = 0
    while True:
        isPD = _isPD(A3)
        isPD_all = isPD.all()
        if isPD_all or k>=100:
            break
        k+=1
        mineig = cp.amin(cp.linalg.eigvalsh(A3),axis=-1)
        assert cp.isfinite(mineig).all()
        A3 += (~isPD[...,None,None] * I) * (-mineig * k**2 + spacing)[...,None,None]
    #print(k)
    return A3

# %% ../nbs/API/co.ipynb 27
def regularize_spectral(coh:cp.ndarray, # stack of matrix with shape [...,N,N]
                        beta:Union[float, cp.ndarray], # the regularization parameter, a float number or cupy ndarray with shape [...]
                        )-> cp.ndarray: # regularized matrix, shape [...,N,N]
    '''
    Spectral regularizer for coherence matrix.
    '''
    I = cp.eye(coh.shape[-1],dtype=coh.dtype)
    beta = cp.asarray(beta)[...,None,None]

    regularized_coh = (1-beta)*coh + beta* I
    return regularized_coh
