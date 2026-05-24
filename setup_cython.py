"""Cython compilation — compile core modules to .so for IP protection + performance.

Usage:
    LARGESTACK_CYTHON=1 python setup_cython.py build_ext --inplace
    
Compiles: _core/, _guard/, _memory/ → .so files (3-5x speedup on hot paths)
"""
import os, sys
from setuptools import setup, find_packages

CYTHON_MODULES = [
    "largestack/_core/engine.py",
    "largestack/_core/gateway.py",
    "largestack/_core/cost.py",
    "largestack/_core/loop_guard.py",
    "largestack/_core/circuit_breaker.py",
    "largestack/_core/semantic_cache.py",
    "largestack/_core/smart_router.py",
    "largestack/_guard/pii.py",
    "largestack/_guard/injection.py",
    "largestack/_guard/toxicity.py",
    "largestack/_guard/hallucination.py",
    "largestack/_guard/pipeline.py",
    "largestack/_memory/buffer.py",
    "largestack/_memory/semantic.py",
    "largestack/_memory/graph.py",
    "largestack/_memory/episodic.py",
    "largestack/_rag/chunker.py",
    "largestack/_rag/retriever.py",
    "largestack/_rag/reranker.py",
    "largestack/_rag/embedder.py",
    "largestack/_security/encryption.py",
    "largestack/_security/permissions.py",
    "largestack/_security/vault.py",
    "largestack/_observe/anomaly.py",
]

if os.environ.get("LARGESTACK_CYTHON", "0") == "1":
    try:
        from Cython.Build import cythonize
        from Cython.Distutils import build_ext
        
        # Convert .py paths to proper Extension format
        ext_modules = cythonize(
            CYTHON_MODULES,
            compiler_directives={
                "language_level": "3",
                "boundscheck": False,
                "wraparound": False,
                "cdivision": True,
            },
            nthreads=os.cpu_count() or 4,
        )
        
        setup(
            name="largestack",
            version="1.0.1",
            packages=find_packages(),
            ext_modules=ext_modules,
            cmdclass={"build_ext": build_ext},
        )
        
        print(f"\n✓ Compiled {len(CYTHON_MODULES)} modules to .so files")
        
    except ImportError:
        print("ERROR: Cython not installed. Run: pip install cython")
        sys.exit(1)
else:
    print("Cython compilation disabled. Set LARGESTACK_CYTHON=1 to enable.")
    print(f"  Would compile {len(CYTHON_MODULES)} modules:")
    for m in CYTHON_MODULES:
        print(f"    {m}")
