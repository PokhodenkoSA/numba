from __future__ import print_function, absolute_import
import math
import numpy as np
from numba import ocl, float64, int8, int32
from numba.ocl.testing import unittest


def cu_mat_power(A, power, power_A):
    y, x = ocl.grid(2)

    m, n = power_A.shape
    if x >= n or y >= m:
        return

    power_A[y, x] = math.pow(A[y, x], int32(power))


def cu_mat_power_binop(A, power, power_A):
    y, x = ocl.grid(2)

    m, n = power_A.shape
    if x >= n or y >= m:
        return

    power_A[y, x] = A[y, x] ** power


class TestOclPowi(unittest.TestCase):
    def test_powi(self):
        dec = ocl.jit(argtypes=[float64[:, :], int8, float64[:, :]])
        kernel = dec(cu_mat_power)

        power = 2
        A = np.arange(10, dtype=np.float64).reshape(2, 5)
        Aout = np.empty_like(A)
        kernel[1, A.shape](A, power, Aout)
        self.assertTrue(np.allclose(Aout, A ** power))

    def test_powi_binop(self):
        dec = ocl.jit(argtypes=[float64[:, :], int8, float64[:, :]])
        kernel = dec(cu_mat_power_binop)

        power = 2
        A = np.arange(10, dtype=np.float64).reshape(2, 5)
        Aout = np.empty_like(A)
        kernel[1, A.shape](A, power, Aout)
        self.assertTrue(np.allclose(Aout, A ** power))


if __name__ == '__main__':
    unittest.main()

