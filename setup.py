"""Cython build configuration for LARGESTACK Agentic AI Framework.

Compiles largestack/_core/, _guard/, _memory/, _observe/, _orchestrate/, _rag/ to .so files.
Directives: embedsignature=False, emit_code_comments=False, annotate=False
Post-build: strip --strip-all *.so
"""
import os, sys
from setuptools import setup, find_packages

USE_CYTHON = os.environ.get("LARGESTACK_CYTHON", "0") == "1"

if USE_CYTHON:
    try:
        from Cython.Build import cythonize
        
        COMPILE_DIRS = [
            "largestack/_core/*.py",
            "largestack/_core/providers/*.py",
            "largestack/_guard/*.py",
            "largestack/_memory/*.py",
            "largestack/_observe/*.py",
            "largestack/_orchestrate/*.py",
            "largestack/_rag/*.py",
            "largestack/_test/*.py",
        ]
        
        ext_modules = cythonize(
            COMPILE_DIRS,
            compiler_directives={
                "language_level": "3",
                "embedsignature": False,
                "emit_code_comments": False,
                "annotation_typing": False,
            },
            annotate=False,
            exclude=["*/__init__.py"],
        )
        
        setup(ext_modules=ext_modules)
    except ImportError:
        print("Cython not installed. Building pure Python.")
        setup()
else:
    setup()
