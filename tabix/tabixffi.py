"""
>>> t = Tabix('tabix/C/example.gtf.gz')
>>> t.sequences
[u'chr1', u'chr2']

>>> for item in t('chr1'):
...    print item[:40].split()
...    break
['chr1', 'ENSEMBL', 'UTR', '1737', '2090', '.', '+', '.', 'gene_id']

>>> for item in t('chr1:2090-3000'):
...    print item[:40].split()
...    break
['chr1', 'ENSEMBL', 'UTR', '1737', '2090', '.', '+', '.', 'gene_id']

>>> t
Tabix('tabix/C/example.gtf.gz')

>>> del t
"""

import os.path as op
from glob import glob
from cffi import FFI

ffi = FFI()
ffi.cdef("""

struct __ti_index_t;
typedef struct __ti_index_t ti_index_t;

struct __ti_iter_t;
typedef struct __ti_iter_t *ti_iter_t;

typedef struct {
    ti_index_t *idx;
    ...;
} tabix_t;

typedef struct {
        int32_t preset;
        int32_t sc, bc, ec; // seq col., beg col. and end col.
        int32_t meta_char, line_skip;
} ti_conf_t;

tabix_t *ti_open(const char *fn, const char *fnidx);
int ti_lazy_index_load(tabix_t *t);
int ti_index_build(const char *fn, const ti_conf_t *conf);
void ti_close(tabix_t *t);
void free (void* ptr);

const char **ti_seqname(const ti_index_t *idx, int *n);

ti_iter_t ti_query(tabix_t *t, const char *name, int beg, int end);
ti_iter_t ti_querys(tabix_t *t, const char *reg);

const char *ti_read(tabix_t *t, ti_iter_t iter, int *len);
void ti_iter_destroy(ti_iter_t iter);

const ti_conf_t *ti_get_conf(ti_index_t *idx);

void ti_index_destroy(ti_index_t *idx);
""")

path = op.relpath(op.dirname(__file__))

cfiles = [x for x in glob("%s/C/*.c" % path) if not x.endswith("main.c")]
hfiles = [h for h in glob('%s/C/*.h' % path)]

C = ffi.verify('''
#include "stdlib.h"
#include "tabix.h"
''',
    libraries=['c', 'z'],
    depends=hfiles + cfiles,
    sources=cfiles,
    include_dirs=["%s/C" % path],
    ext_package='tabixffi'
)

class Tabix(object):
    def __init__(self, fn):
        if op.exists(fn + ".tbi"):
            self._tabix = C.ti_open(fn, ffi.NULL)
        else: # try to create the index.
            if fn.endswith('.bed.gz'):
                Tabix.build(fn)
            elif fn.endswith(('.gff.gz', '.gtf.gz')):
                Tabix.build(fn, 1, 4, 5, '#', 0)
            elif fn.endswith(('.vcf.gz')):
                Tabix.build(fn, 1, 2, 0, '#', 0)
            else:
                raise Exception('%s.tbi not found and filetype not known' % fn)
            self._tabix = C.ti_open(fn, ffi.NULL)
        C.ti_lazy_index_load(self._tabix)
        self._conf = C.ti_get_conf(self._tabix.idx)
        self.fn = fn

    @property
    def sequences(self):
        n = ffi.new("int *")
        cnames = C.ti_seqname(self._tabix.idx, n)
        try:
            names = [ffi.string(cnames[i]).decode() for i in range(n[0])]
            return names
        finally:
            C.free(cnames)

    @classmethod
    def build(cls, fname, seq_col=1, start_col=2, end_col=3, comment="#",
                 line_skip=0):
        """
        1-based columns
        """
        conf = ffi.new('ti_conf_t *')
        conf.sc, conf.bc, conf.ec = seq_col, start_col, end_col
        conf.meta_char = ffi.cast('char', comment)
        conf.preset = 0
        conf.line_skip = line_skip
        assert C.ti_index_build(fname, conf) != -1
        return Tabix(fname)

    def __call__(self, region, start=None, end=None, convert=False):
        if start is None:
            assert end is None
            t_iter = C.ti_querys(self._tabix, region)
        else:
            t_iter = C.ti_query(self._tabix, region, start, end)

        s_len = ffi.new("int *")
        # TODO: could yield a feature with start, end as ints.
        start_col, end_col = self._conf.bc, self._conf.ec
        n_hits = s_len[0]
        try:
            next_rec = C.ti_read(self._tabix, t_iter, s_len)
            while next_rec:
                yield ffi.string(next_rec)
                next_rec = C.ti_read(self._tabix, t_iter, s_len)
        finally:
            C.ti_iter_destroy(t_iter)

    query = __call__

    def __del__(self):
        try:
            C.ti_index_destroy(self._tabix)
            self.close()
        except:
            pass

    def close(self):
        C.ti_close(self._tabix)

    def __repr__(self):
        return "%s('%s')" % (self.__class__.__name__, self.fn)

if __name__ == "__main__":

    import doctest
    doctest.testmod()
