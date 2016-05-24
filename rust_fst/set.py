from contextlib import contextmanager

from .common import KeyStreamIterator
from .lib import ffi, lib, checked_call


class SetBuilder(object):
    def insert(self, val):
        raise NotImplementedError

    def finish(self):
        raise NotImplementedError


class FileSetBuilder(SetBuilder):
    def __init__(self, fpath):
        self._ctx = lib.fst_context_new()
        self._writer_p = checked_call(
            lib.fst_bufwriter_new, self._ctx, fpath.encode('utf8'))
        self._builder_p = checked_call(
            lib.fst_filesetbuilder_new, self._ctx, self._writer_p)

    def insert(self, val):
        c_str = ffi.new("char[]", val.encode('utf8'))
        checked_call(lib.fst_filesetbuilder_insert,
                     self._ctx, self._builder_p, c_str)

    def finish(self):
        checked_call(lib.fst_filesetbuilder_finish,
                     self._ctx, self._builder_p)
        lib.fst_bufwriter_free(self._writer_p)
        lib.fst_context_free(self._ctx)


class MemSetBuilder(SetBuilder):
    def __init__(self):
        self._ctx = lib.fst_context_new()
        self._ptr = lib.fst_memsetbuilder_new()
        self._set_ptr = None

    def insert(self, val):
        c_str = ffi.new("char[]", val.encode('utf8'))
        checked_call(lib.fst_memsetbuilder_insert, self._ctx, self._ptr, c_str)

    def finish(self):
        self._set_ptr = checked_call(lib.fst_memsetbuilder_finish,
                                     self._ctx, self._ptr)
        lib.fst_context_free(self._ctx)
        self._ctx = None
        self._ptr = None

    def get_set(self):
        if self._set_ptr is None:
            raise ValueError("The builder has to be finished first.")
        return FstSet(pointer=self._set_ptr)


class OpBuilder(object):
    def __init__(self, set_ptr):
        # NOTE: No need for `ffi.gc`, since the struct will be free'd
        #       once we call union/intersection/difference
        self._ptr = lib.fst_set_make_opbuilder(set_ptr)

    def push(self, set_ptr):
        lib.fst_set_opbuilder_push(self._ptr, set_ptr)

    def union(self):
        stream_ptr = lib.fst_set_opbuilder_union(self._ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_union_next,
                                 lib.fst_set_union_free)

    def intersection(self):
        stream_ptr = lib.fst_set_opbuilder_intersection(self._ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_intersection_next,
                                 lib.fst_set_intersection_free)

    def difference(self):
        stream_ptr = lib.fst_set_opbuilder_difference(self._ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_difference_next,
                                 lib.fst_set_difference_free)

    def symmetric_difference(self):
        stream_ptr = lib.fst_set_opbuilder_symmetricdifference(self._ptr)
        return KeyStreamIterator(stream_ptr,
                                 lib.fst_set_symmetricdifference_next,
                                 lib.fst_set_symmetricdifference_free)


class FstSet(object):
    """ An immutable set backed by a finite state transducer stored on disk.

    The interface tries to follow the `frozenset` type as much as possible.
    """
    @staticmethod
    @contextmanager
    def build(fpath=None):
        """ Context manager to build a new FST set in a given file.

        Keys must be inserted in lexicographical order.

        See http://burntsushi.net/rustdoc/fst/struct.SetBuilder.html for more
        details.
        """
        if fpath:
            builder = FileSetBuilder(fpath)
        else:
            builder = MemSetBuilder()
        yield builder
        builder.finish()

    @classmethod
    def from_iter(cls, it, fpath=None):
        with cls.build(fpath) as builder:
            for key in it:
                builder.insert(key)
        if fpath:
            return cls(path=fpath)
        else:
            return builder.get_set()

    def __init__(self, path=None, pointer=None):
        """ Load an FST set from a given file. """
        self._ctx = ffi.gc(lib.fst_context_new(), lib.fst_context_free)
        if path:
            s = checked_call(lib.fst_set_open, self._ctx,
                             ffi.new("char[]", path.encode('utf8')))
        else:
            s = pointer
        self._ptr = ffi.gc(s, lib.fst_set_free)

    def __contains__(self, val):
        return lib.fst_set_contains(
            self._ptr, ffi.new("char[]", val.encode('utf8')))

    def __iter__(self):
        stream_ptr = lib.fst_set_stream(self._ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_stream_next,
                                 lib.fst_set_stream_free)

    def __len__(self):
        return int(lib.fst_set_len(self._ptr))

    def __getitem__(self, s):
        if not isinstance(s, slice):
            raise ValueError(
                "Value must be a string slice (e.g. `['foo':]`)")
        if s.start and s.stop and s.start > s.stop:
            raise ValueError(
                "Start key must be lexicographically smaller than stop.")
        sb_ptr = lib.fst_set_streambuilder_new(self._ptr)
        if s.start:
            c_start = ffi.new("char[]", s.start.encode('utf8'))
            sb_ptr = lib.fst_set_streambuilder_add_ge(sb_ptr, c_start)
        if s.stop:
            c_stop = ffi.new("char[]", s.stop.encode('utf8'))
            sb_ptr = lib.fst_set_streambuilder_add_lt(sb_ptr, c_stop)
        stream_ptr = lib.fst_set_streambuilder_finish(sb_ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_stream_next,
                                 lib.fst_set_stream_free)

    def _make_opbuilder(self, *others):
        opbuilder = OpBuilder(self._ptr)
        for oth in others:
            opbuilder.push(oth._ptr)
        return opbuilder

    def union(self, *others):
        return self._make_opbuilder(*others).union()

    def intersection(self, *others):
        return self._make_opbuilder(*others).intersection()

    def difference(self, *others):
        return self._make_opbuilder(*others).difference()

    def symmetric_difference(self, *others):
        return self._make_opbuilder(*others).symmetric_difference()

    def issubset(self, other):
        return bool(lib.fst_set_issubset(self._ptr, other._ptr))

    def issuperset(self, other):
        return bool(lib.fst_set_issuperset(self._ptr, other._ptr))

    def isdisjoint(self, other):
        return bool(lib.fst_set_isdisjoint(self._ptr, other._ptr))

    def search_re(self, pattern):
        """ Search the set with a regular expression.

        Note that the regular expression syntax is not Python's, but the one
        supported by the `regex` Rust crate, which is almost identical
        to the engine of the RE2 engine.

        For a documentation of the syntax, see:
        http://doc.rust-lang.org/regex/regex/index.html#syntax

        Due to limitations of the underlying FST, only a subset of this syntax
        is supported. Most notably absent are:
            - Lazy quantifiers (r'*?', r'+?')
            - Word boundaries (r'\b')
            - Other zero-width assertions (r'^', r'$')
        For background on these limitations, consult the documentation of
        the Rust crate: http://burntsushi.net/rustdoc/fst/struct.Regex.html

        :param pattern:     A regular expression
        :returns:           An iterator over all matching keys in the set
        :rtype:             :py:class:`KeyStreamIterator`
        """
        re_ptr = checked_call(
            lib.fst_regex_new, self._ctx,
            ffi.new("char[]", pattern.encode('utf8')))
        stream_ptr = lib.fst_set_regexsearch(self._ptr, re_ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_regexstream_next,
                                 lib.fst_set_regexstream_free, re_ptr,
                                 lib.fst_regex_free)

    def search(self, term, max_dist):
        """ Search the set with a Levenshtein automaton.

        :param term:        The search term
        :param max_dist:    The maximum edit distance for search results
        :returns:           Iterator over matching values in the set
        :rtype:             KeyStreamIterator
        """
        lev_ptr = checked_call(
            lib.fst_levenshtein_new, self._ctx,
            ffi.new("char[]", term.encode('utf8')), max_dist)
        stream_ptr = lib.fst_set_levsearch(self._ptr, lev_ptr)
        return KeyStreamIterator(stream_ptr, lib.fst_set_levstream_next,
                                 lib.fst_set_levstream_free, lev_ptr,
                                 lib.fst_levenshtein_free)
