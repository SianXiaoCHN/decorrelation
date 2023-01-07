# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/API/shp.ipynb.

# %% auto 0
__all__ = ['ks_test']

# %% ../nbs/API/shp.ipynb 4
import cupy as cp
import math

# %% ../nbs/API/shp.ipynb 6
# It looks cupy do not support pointer to pointer: float** rmli_stack
# These code are modified from https://dev.thep.lu.se/yat under GPLv3 license.
_ks_test_kernel = cp.ElementwiseKernel(
    'raw T rmli_stack, int32 nlines, int32 width, int32 nimages, int32 az_half_win, int32 r_half_win',
    'raw T dist, raw T p',
    '''
    int az_win = 2*az_half_win+1;
    int r_win = 2*r_half_win+1;
    int win = az_win*r_win;
    
    int ref_idx = i/win;
    int ref_az = ref_idx/width;
    int ref_r = ref_idx -ref_az*width;
    
    int win_idx = i - ref_idx*win;
    int win_az = win_idx/r_win;
    int win_r = win_idx - win_az*r_win;
    int sec_az = ref_az + win_az - az_half_win;
    int sec_r = ref_r + win_r - r_half_win;
    int sec_idx = sec_az*width + sec_r;
    
    if (ref_r >= width && ref_az >= nlines) {
        return;
    }
    if (sec_az < 0 || sec_az >= nlines || sec_r < 0 || sec_r >= width) {
        dist[ref_idx*win+win_az*r_win+win_r] = -1.0;
        p[ref_idx*win+win_az*r_win+win_r] = -1.0;
        return;
    }
    
    // Compute the maximum difference between the cumulative distributions
    int j1 = 0, j2 = 0;
    T f1, f2, d, dmax = 0.0, en = nimages;

    while (j1 < nimages && j2 < nimages) {
        f1 = rmli_stack[ref_idx*nimages + j1];
        f2 = rmli_stack[sec_idx*nimages + j2];
        if (f1 <= f2) j1++;
        if (f1 >= f2) j2++;
        d = fabs((j2-j1)/en);
        if (d > dmax) dmax = d;
    }
    en=sqrt(en/2);
    p[ref_idx*win+win_az*r_win+win_r] = ks_p((en+0.12+0.11/en)*dmax);
    dist[ref_idx*win+win_az*r_win+win_r] = dmax;
    ''',
    name = 'ks_test_kernel',no_return=True,
    preamble = '''
    __device__ T ks_p(T x)
    {
        T x2 = -2.0*x*x;
        int sign = 1;
        T p = 0.0,p2 = 0.0;
    
        for (int i = 1; i <= 100; i++) {
            p += sign*2*exp(x2*i*i);
            if (p==p2) return p;
            sign = -sign;
            p2 = p;
        }
        return p;
    }
    ''',)

# %% ../nbs/API/shp.ipynb 7
def ks_test(rmli_stack:cp.ndarray, # the rmli stack, dtype: cupy.floating
            az_half_win:int, # SHP identification half search window size in azimuth direction
            r_half_win:int, # SHP identification half search window size in range direction
            block_size:int=128, # the CUDA block size, it only affects the calculation speed
           ) -> tuple : # the KS test statistics `dist` and p value `p`
    '''
    SHP identification based on Two-Sample Kolmogorov-Smirnov Test
    '''
    az_win = 2*az_half_win+1
    r_win = 2*r_half_win+1
    nlines = rmli_stack.shape[0]
    width = rmli_stack.shape[1]
    nimages = rmli_stack.shape[-1]
    dist = cp.empty((nlines,width,az_win,r_win),dtype=rmli_stack.dtype)
    p = cp.empty((nlines,width,az_win,r_win),dtype=rmli_stack.dtype)

    _ks_test_kernel(rmli_stack,cp.int32(nlines),cp.int32(width),cp.int32(nimages),
                    cp.int32(az_half_win),cp.int32(r_half_win),dist,p,
                    size=width*nlines*r_win*az_win,block_size=block_size)
    return dist,p
