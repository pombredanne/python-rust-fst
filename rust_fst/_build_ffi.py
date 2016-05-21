from cffi import FFI

ffi = FFI()
ffi.set_source('rust_fst._ffi', None)
ffi.cdef("""
    typedef struct {
        bool  has_error;
        char* error_type;
        char* error_description;
        char* error_display;
        char* error_debug;
    } Context;

    typedef struct FileSetBuilder_S FileSetBuilder;
    typedef struct MemSetBuilder_S MemSetBuilder;
    typedef struct BufWriter_S BufWriter;
    typedef struct Set_S Set;
    typedef struct Stream_S Stream;
    typedef struct Levenshtein_S Levenshtein;
    typedef struct LevStream_S LevStream;

    Context* context_new();
    void fst_context_free(Context*);

    void fst_string_free(char*);

    BufWriter* fst_bufwriter_new(Context*, char*);
    void fst_bufwriter_free(BufWriter*);

    FileSetBuilder* fst_filesetbuilder_new(Context*, BufWriter*);
    void fst_filesetbuilder_insert(Context*, FileSetBuilder*, char*);
    void fst_filesetbuilder_finish(Context*, FileSetBuilder*);

    MemSetBuilder* fst_memsetbuilder_new();
    bool fst_memsetbuilder_insert(Context*, MemSetBuilder*, char*);
    Set* fst_memsetbuilder_finish(Context*, MemSetBuilder*);

    Set* fst_set_open(Context*, char*);
    bool fst_set_contains(Set*, char*);
    size_t fst_set_len(Set*);
    bool fst_set_isdisjoint(Set*, Set*);
    bool fst_set_issubset(Set*, Set*);
    bool fst_set_issuperset(Set*, Set*);
    Stream* fst_set_stream(Set*);
    LevStream* fst_set_levsearch(Set*, Levenshtein*);
    void fst_set_free(Set*);

    char* fst_setstream_next(Stream*);
    void fst_setstream_free(Stream*);

    char* fst_levstream_next(LevStream*);
    void fst_levstream_free(LevStream*);

    Levenshtein* fst_levenshtein_new(Context*, char*, uint32_t);
    void fst_levenshtein_free(Levenshtein*);
""")

if __name__ == '__main__':
    ffi.compile()
