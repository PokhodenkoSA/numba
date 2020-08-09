"""
Unspecified error handling tests
"""

import numpy as np
import os

from numba import jit, njit, typed, int64, types
from numba.core import errors
import numba.core.typing.cffi_utils as cffi_support
from numba.extending import (overload, intrinsic, overload_method,
                             overload_attribute)
from numba.core.compiler import CompilerBase
from numba.core.untyped_passes import (TranslateByteCode, FixupArgs,
                                       IRProcessing,)
from numba.core.typed_passes import (NopythonTypeInference, DeadCodeElimination,
                                     NoPythonBackend)
from numba.core.compiler_machinery import PassManager
from numba.core.types.functions import _err_reasons as error_reasons

from numba.tests.support import skip_parfors_unsupported
import unittest

# used in TestMiscErrorHandling::test_handling_of_write_to_*_global
_global_list = [1, 2, 3, 4]
_global_dict = typed.Dict.empty(int64, int64)


class TestErrorHandlingBeforeLowering(unittest.TestCase):

    def test_unsupported_make_function_return_inner_func(self):
        def func(x):
            """ return the closure """
            z = x + 1

            def inner(x):
                return x + z
            return inner

        for pipeline in jit, njit:
            with self.assertRaises(errors.TypingError) as raises:
                pipeline(func)(1)

            expected = "Cannot capture the non-constant value"
            self.assertIn(expected, str(raises.exception))


class TestUnsupportedReporting(unittest.TestCase):

    def test_unsupported_numpy_function(self):
        # np.asanyarray(list) currently unsupported
        @njit
        def func():
            np.asanyarray([1,2,3])

        with self.assertRaises(errors.TypingError) as raises:
            func()

        expected = "Use of unsupported NumPy function 'numpy.asanyarray'"
        self.assertIn(expected, str(raises.exception))


class TestMiscErrorHandling(unittest.TestCase):

    def test_use_of_exception_for_flow_control(self):
        # constant inference uses exceptions with no Loc specified to determine
        # flow control, this asserts that the construction of the lowering
        # error context handler works in the case of an exception with no Loc
        # specified. See issue #3135.
        @njit
        def fn(x):
            return 10**x

        a = np.array([1.0],dtype=np.float64)
        fn(a) # should not raise

    def test_commented_func_definition_is_not_a_definition(self):
        # See issue #4056, the commented def should not be found as the
        # definition for reporting purposes when creating the synthetic
        # traceback because it is commented! Use of def in docstring would also
        # cause this issue hence is tested.

        def foo_commented():
            #def commented_definition()
            raise Exception('test_string')

        def foo_docstring():
            """ def docstring containing def might match function definition!"""
            raise Exception('test_string')

        for func in (foo_commented, foo_docstring):
            with self.assertRaises(Exception) as raises:
                func()

            self.assertIn("test_string", str(raises.exception))

    def test_use_of_ir_unknown_loc(self):
        # for context see # 3390
        class TestPipeline(CompilerBase):
            def define_pipelines(self):
                name = 'bad_DCE_pipeline'
                pm = PassManager(name)
                pm.add_pass(TranslateByteCode, "analyzing bytecode")
                pm.add_pass(FixupArgs, "fix up args")
                pm.add_pass(IRProcessing, "processing IR")
                # remove dead before type inference so that the Arg node is
                # removed and the location of the arg cannot be found
                pm.add_pass(DeadCodeElimination, "DCE")
                # typing
                pm.add_pass(NopythonTypeInference, "nopython frontend")
                pm.add_pass(NoPythonBackend, "nopython mode backend")
                pm.finalize()
                return [pm]

        @njit(pipeline_class=TestPipeline)
        def f(a):
            return 0

        with self.assertRaises(errors.TypingError) as raises:
            f(iter([1,2]))  # use a type that Numba doesn't recognize

        expected = 'File "unknown location", line 0:'
        self.assertIn(expected, str(raises.exception))

    def check_write_to_globals(self, func):
        with self.assertRaises(errors.TypingError) as raises:
            func()

        expected = ["The use of a", "in globals, is not supported as globals"]
        for ex in expected:
            self.assertIn(ex, str(raises.exception))

    def test_handling_of_write_to_reflected_global(self):
        @njit
        def foo():
            _global_list[0] = 10

        self.check_write_to_globals(foo)

    def test_handling_of_write_to_typed_dict_global(self):
        @njit
        def foo():
            _global_dict[0] = 10

        self.check_write_to_globals(foo)

    @skip_parfors_unsupported
    def test_handling_forgotten_numba_internal_import(self):
        @njit(parallel=True)
        def foo():
            for i in prange(10): # noqa: F821 prange is not imported
                pass

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        expected = ("'prange' looks like a Numba internal function, "
                    "has it been imported")
        self.assertIn(expected, str(raises.exception))

    def test_handling_unsupported_generator_expression(self):
        def foo():
            (x for x in range(10))

        expected = "The use of yield in a closure is unsupported."

        for dec in jit(forceobj=True), njit:
            with self.assertRaises(errors.UnsupportedError) as raises:
                dec(foo)()
            self.assertIn(expected, str(raises.exception))

    def test_handling_undefined_variable(self):
        @njit
        def foo():
            return a # noqa: F821

        expected = "NameError: name 'a' is not defined"

        with self.assertRaises(errors.TypingError) as raises:
            foo()
        self.assertIn(expected, str(raises.exception))


class TestConstantInferenceErrorHandling(unittest.TestCase):

    def test_basic_error(self):
        # issue 3717
        @njit
        def problem(a,b):
            if a == b:
                raise Exception("Equal numbers: %i %i", a, b)
            return a * b

        with self.assertRaises(errors.ConstantInferenceError) as raises:
            problem(1,2)

        msg1 = "Constant inference not possible for: arg(0, name=a)"
        msg2 = 'raise Exception("Equal numbers: %i %i", a, b)'
        self.assertIn(msg1, str(raises.exception))
        self.assertIn(msg2, str(raises.exception))


class TestErrorMessages(unittest.TestCase):

    def test_specific_error(self):

        given_reason = "specific_reason"

        def foo():
            pass

        @overload(foo)
        def ol_foo():
            raise ValueError(given_reason)

        @njit
        def call_foo():
            foo()

        with self.assertRaises(errors.TypingError) as raises:
            call_foo()

        excstr = str(raises.exception)
        self.assertIn(error_reasons['specific_error'].splitlines()[0], excstr)
        self.assertIn(given_reason, excstr)

    def test_no_match_error(self):

        def foo():
            pass

        @overload(foo)
        def ol_foo():
            return None # emulate no impl available for type

        @njit
        def call_foo():
            foo()

        with self.assertRaises(errors.TypingError) as raises:
            call_foo()

        excstr = str(raises.exception)
        self.assertIn("No match", excstr)

    def test_error_function_source_is_correct(self):
        """ Checks that the reported source location for an overload is the
        overload implementation source, not the actual function source from the
        target library."""

        @njit
        def foo():
            np.linalg.svd("chars")

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn(error_reasons['specific_error'].splitlines()[0], excstr)
        expected_file = os.path.join("numba", "np", "linalg.py")
        expected = f"Overload in function 'svd_impl': File: {expected_file}:"
        self.assertIn(expected.format(expected_file), excstr)

    def test_concrete_template_source(self):
        # hits ConcreteTemplate
        @njit
        def foo():
            return 'a' + 1

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)

        self.assertIn("Operator Overload in function 'add'", excstr)
        # there'll be numerous matched templates that don't work
        self.assertIn("<numerous>", excstr)

    def test_abstract_template_source(self):
        # hits AbstractTemplate
        @njit
        def foo():
            return len(1)

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Overload of function 'len'", excstr)

    def test_callable_template_source(self):
        # hits CallableTemplate
        @njit
        def foo():
            return np.angle(1)

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Overload of function 'angle'", excstr)

    def test_overloadfunction_template_source(self):
        # hits _OverloadFunctionTemplate
        def bar(x):
            pass

        @overload(bar)
        def ol_bar(x):
            pass

        @njit
        def foo():
            return bar(1)

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        # there will not be "numerous" matched templates, there's just one,
        # the one above, so assert it is reported
        self.assertNotIn("<numerous>", excstr)
        expected_file = os.path.join("numba", "tests",
                                     "test_errorhandling.py")
        expected_ol = f"Overload of function 'bar': File: {expected_file}:"
        self.assertIn(expected_ol.format(expected_file), excstr)
        self.assertIn("No match.", excstr)

    def test_intrinsic_template_source(self):
        # hits _IntrinsicTemplate
        given_reason1 = "x must be literal"
        given_reason2 = "array.ndim must be 1"

        @intrinsic
        def myintrin(typingctx, x, arr):
            if not isinstance(x, types.IntegerLiteral):
                raise errors.RequireLiteralValue(given_reason1)

            if arr.ndim != 1:
                raise ValueError(given_reason2)

            sig = types.intp(x, arr)

            def codegen(context, builder, signature, args):
                pass
            return sig, codegen

        @njit
        def call_intrin():
            arr = np.zeros((2, 2))
            myintrin(1, arr)

        with self.assertRaises(errors.TypingError) as raises:
            call_intrin()

        excstr = str(raises.exception)
        self.assertIn(error_reasons['specific_error'].splitlines()[0], excstr)
        self.assertIn(given_reason1, excstr)
        self.assertIn(given_reason2, excstr)
        self.assertIn("Intrinsic in function", excstr)

    def test_overloadmethod_template_source(self):
        # doesn't hit _OverloadMethodTemplate for source as it's a nested
        # exception
        @overload_method(types.UnicodeType, 'isnonsense')
        def ol_unicode_isnonsense(self):
            pass

        @njit
        def foo():
            "abc".isnonsense()

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Overload of function 'ol_unicode_isnonsense'", excstr)

    def test_overloadattribute_template_source(self):
        # doesn't hit _OverloadMethodTemplate for source as it's a nested
        # exception
        @overload_attribute(types.UnicodeType, 'isnonsense')
        def ol_unicode_isnonsense(self):
            pass

        @njit
        def foo():
            "abc".isnonsense

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Overload of function 'ol_unicode_isnonsense'", excstr)

    def test_external_function_pointer_template_source(self):
        from numba.tests.ctypes_usecases import c_cos

        @njit
        def foo():
            c_cos('a')

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Type Restricted Function in function 'unknown'", excstr)

    @unittest.skipUnless(cffi_support.SUPPORTED, "CFFI not supported")
    def test_cffi_function_pointer_template_source(self):
        from numba.tests import cffi_usecases as mod
        mod.init()
        func = mod.cffi_cos

        @njit
        def foo():
            func('a')

        with self.assertRaises(errors.TypingError) as raises:
            foo()

        excstr = str(raises.exception)
        self.assertIn("Type Restricted Function in function 'unknown'", excstr)


if __name__ == '__main__':
    unittest.main()
