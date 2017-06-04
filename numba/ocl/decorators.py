from __future__ import print_function, absolute_import, division
from numba import config, sigutils, types
from warnings import warn
from .compiler import (compile_kernel, compile_device, declare_device_function,
                       AutoJitOCLKernel, compile_device_template)


def jitdevice(func, link=[], debug=None, inline=False):
    """Wrapper for device-jit.
    """
    debug = config.OCL_DEBUGINFO_DEFAULT if debug is None else debug
    if link:
        raise ValueError("link keyword invalid for device function")
    return compile_device_template(func, debug=debug, inline=inline)


def jit(func_or_sig=None, argtypes=None, device=False, inline=False, bind=True,
        link=[], debug=None, **kws):
    """
    JIT compile a python function conforming to the OpenCL Python specification.
    If a signature is supplied, then a function is returned that takes a
    function to compile. If

    :param func_or_sig: A function to JIT compile, or a signature of a function
       to compile. If a function is supplied, then an :class:`AutoJitOCLKernel`
       is returned. If a signature is supplied, then a function which takes a
       function to compile and returns an :class:`AutoJitOCLKernel` is
       returned.

       .. note:: A kernel cannot have any return value.
    :type func_or_sig: function or numba.typing.Signature
    :param device: Indicates whether this is a device function.
    :type device: bool
    :param bind: Force binding to OpenCL context immediately
    :type bind: bool
    :param link: A list of files containing PTX source to link with the function
    :type link: list
    :param debug: If True, check for exceptions thrown when executing the
       kernel. Since this degrades performance, this should only be used for
       debugging purposes.  Defaults to False.  (The default value can be
       overriden by setting environment variable ``NUMBA_OCL_DEBUGINFO=1``.)
    :param fastmath: If true, enables flush-to-zero and fused-multiply-add,
       disables precise division and square root. This parameter has no effect
       on device function, whose fastmath setting depends on the kernel function
       from which they are called.
    """
    debug = config.OCL_DEBUGINFO_DEFAULT if debug is None else debug

    fastmath = kws.get('fastmath', False)
    if argtypes is None and not sigutils.is_signature(func_or_sig):
        if func_or_sig is None:
            def autojitwrapper(func):
                return jit(func, device=device, bind=bind, debug=debug, **kws)
            return autojitwrapper
        # func_or_sig is a function
        else:
            if device:
                return jitdevice(func_or_sig, debug=debug, **kws)
            else:
                targetoptions = kws.copy()
                targetoptions['debug'] = debug
                return AutoJitOCLKernel(func_or_sig, bind=bind, targetoptions=targetoptions)

    else:
        restype, argtypes = convert_types(func_or_sig, argtypes)

        if restype and not device and restype != types.void:
            raise TypeError("OCL kernel must have void return type.")

        def kernel_jit(func):
            kernel = compile_kernel(func, argtypes, link=link, debug=debug,
                                    inline=inline, fastmath=fastmath)

            # Force compilation for the current context
            if bind:
                kernel.bind()

            return kernel

        def device_jit(func):
            return compile_device(func, restype, argtypes, inline=inline,
                                  debug=debug)

        if device:
            return device_jit
        else:
            return kernel_jit


def autojit(*args, **kwargs):
    warn('autojit is deprecated and will be removed in a future release. Use jit instead.')
    return jit(*args, **kwargs)


def declare_device(name, restype=None, argtypes=None):
    restype, argtypes = convert_types(restype, argtypes)
    return declare_device_function(name, restype, argtypes)


def convert_types(restype, argtypes):
    # eval type string
    if sigutils.is_signature(restype):
        assert argtypes is None
        argtypes, restype = sigutils.normalize_signature(restype)

    return restype, argtypes

