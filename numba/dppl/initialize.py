from __future__ import absolute_import, print_function
import llvmlite.binding as ll
import os
from ctypes.util import find_library
import logging


def init_jit():
    from numba.dppl.dispatcher import DPPLDispatcher
    return DPPLDispatcher


def initialize_all():
    from numba.core.registry import dispatcher_registry
    dispatcher_registry.ondemand['dppl'] = init_jit

    def load_library_permanently(name):
        lib = find_library(name)
        logging.info(f'LLVM:load_library_permanently: {lib}')
        ll.load_library_permanently(lib)

    load_library_permanently('DPPLOpenCLInterface')
    load_library_permanently('OpenCL')
