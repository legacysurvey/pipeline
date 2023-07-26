import fitsio
import numpy as np
from glob import glob
import os
from legacypipe.survey import LegacySurveyData

'''

This script was used (after creating a symlink farm as described
below) to merge in an updated set of bricks in *sourcedir* into the
symlink farm in *destdir*, specifically the *sourcedir* was re-run
bricks that fixed a sub-blobs issue in DR10; the *destdir* was the new
DR10.1 directory (symlink farm).

It does, for each brick:

- in the source directory, check the checksum file
- look for the known set of output files
- for per-band files, if one file per band is found, demand that all files are found
  (ie, files for a band either all exist or none do)
- assert that all files are in the checksums file
- update the checksums files, merging old & new
- delete target directory 'coadd/B/B' if it is a symlink
- delete any other target files that are symlinks
- rsync files into place
- write updated checksums files

Symlink farm was generated by first creating lists of the 3-character
RA slices (000, 001, ...) that contained no new files, in "sym.txt",
and those that do contain new files in "sb.txt".  The total number of
lines in the two files should be 360.

### Whole RA slices with no updated bricks:

cd ~/cosmo/work/legacysurvey/dr10.1/south

for x in $(cat sym.txt); do ln -s /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/coadd/$x coadd/; done

for x in $(cat sym.txt); do ln -s /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/metrics/$x metrics/; done

for x in $(cat sym.txt); do ln -s /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/tractor/$x tractor/; done

for x in $(cat sym.txt); do ln -s /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/tractor-i/$x tractor-i/; done

### RA slices with updated bricks:

for x in $(cat sb.txt); do echo $x; mkdir coadd/$x;     for y in /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/coadd/$x/*; do ln -s $y coadd/$x/; done; done

for x in $(cat sb.txt); do echo $x; mkdir metrics/$x;   for y in /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/metrics/$x/*; do ln -s $y metrics/$x/; done; done

for x in $(cat sb.txt); do echo $x; mkdir tractor/$x;   for y in /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/tractor/$x/*; do ln -s $y tractor/$x/; done; done

for x in $(cat sb.txt); do echo $x; mkdir tractor-i/$x; for y in /global/cfs/cdirs/cosmo/data/legacysurvey/dr10/south/tractor-i/$x/*; do ln -s $y tractor-i/$x/; done; done

'''

def main():

    sourcedir = '/pscratch/sd/d/dstn/sub-blobs'
    destdir = '/global/cfs/cdirs/cosmo/work/legacysurvey/dr10.1/south'

    bands = ['g','r','i','z']
    wbands = ['W1', 'W2', 'W3', 'W4']
    fns = glob(os.path.join(sourcedir, 'tractor/*/brick-*.sha256sum'))
    fns.sort()
    surveys = {}
    for fn in fns:
        print()
        #print(fn)
        brick = fn.replace('.sha256sum', '')[-8:]
        print('Brick', brick)
        basedir = '/'.join(fn.split('/')[:-3])
        #print('basedir', basedir)
        cmd = 'cd %s && sha256sum --quiet -c %s' % (basedir, fn)
        print(cmd)
        rtn = os.system(cmd)
        #print(rtn)
        assert(rtn == 0)
        shas = open(fn).readlines()
        shas = set([s.strip().split()[1].replace('*','') for s in shas])

        if not basedir in surveys:
            surveys[basedir] = LegacySurveyData(survey_dir=basedir)
        survey = surveys[basedir]

        allfns = []
        for filetype in ['tractor', 'tractor-intermediate', 'ccds-table', 'depth-table',
                         'image-jpeg', 'model-jpeg', 'resid-jpeg',
                         'blobmodel-jpeg',
                         'wise-jpeg', 'wisemodel-jpeg', 'wiseresid-jpeg',
                         'outliers-pre', 'outliers-post',
                         'outliers-masked-pos', 'outliers-masked-neg',
                         'outliers_mask',
                         'blobmap', 'maskbits', 'all-models', 'ref-sources',
                         ]:
            fn = survey.find_file(filetype, brick=brick)
            #print(fn)
            assert(os.path.exists(fn))
            allfns.append(fn.replace(basedir+'/', ''))

        for band in bands:
            for i,filetype in enumerate(['invvar', 'chi2', 'image', 'model', 'blobmodel',
                                         'depth', 'galdepth', 'nexp', 'psfsize',]):
                fn = survey.find_file(filetype, brick=brick, band=band)
                #print(fn)
                exists = os.path.exists(fn)
                # Either all products exist for a band, or none!
                if i == 0:
                    has_band = exists
                else:
                    assert(has_band == exists)
                if has_band:
                    allfns.append(fn.replace(basedir+'/', ''))
            print('Band', band, 'exists:', has_band)

        for band in wbands:
            for i,filetype in enumerate(['invvar', 'image', 'model']):
                fn = survey.find_file(filetype, brick=brick, band=band)
                #print(fn)
                assert(os.path.exists(fn))
                allfns.append(fn.replace(basedir+'/', ''))

        print('sha:', len(shas))
        print('files:', len(allfns))
        #print(shas)
        #print(set(allfns))
        assert(set(shas) == set(allfns))

        # New checksums:
        new_checksums = {}
        fn = survey.find_file('checksums', brick=brick)
        for line in open(fn).readlines():
            words = line.split()
            fn = words[1]
            if fn.startswith('*'):
                fn = fn[1:]
            assert(not(fn.startswith('*')))
            assert(fn in allfns)
            new_checksums[fn] = words[0]
        #print('New checksums:', list(new_checksums.items())[:3])

        new_checksum_files = []

        alldirs = set([os.path.dirname(x) for x in allfns])
        for dirnm in alldirs:
            #print(dirnm)
            pat = os.path.join(destdir, dirnm, '*.sha256sum')
            #print(pat)
            sha = glob(pat)
            checksums = {}

            assert(len(sha) == 1)
            sha = sha[0]
            print('Updating existing checksum file:', sha)
            for line in open(sha).readlines():
                words = line.split()
                fn = words[1]
                if fn.startswith('*'):
                    fn = fn[1:]
                #assert(not(fn.startswith('*')))
                checksums[fn] = words[0]
            #print('Old checksums:', list(checksums.items())[:3])

            nup = 0
            for fn in allfns:
                if not fn.startswith(dirnm):
                    continue
                assert(fn in new_checksums)
                base = os.path.basename(fn)
                assert(base in checksums)
                checksums[base] = new_checksums[fn]
                #print('Updated checksum for', base)
                nup += 1
            print('Updated checksum for', nup, 'files')

            chk_txt = ''.join(['%s *%s\n' % (v,k) for k,v in checksums.items()])
            new_checksum_files.append((sha, chk_txt))

        # Delete existing destination directories
        # (useful when updating some bricks into a symlink farm...)
        for dirnm in ['coadd/%s/%s' % (brick[:3], brick)]:
            path = os.path.join(destdir, dirnm)
            if os.path.islink(path):
                print('Deleting symlink', path)
                os.remove(path)

        # Delete existing destination files
        for fn in allfns:
            path = os.path.join(destdir, fn)
            if os.path.islink(path):
                print('Deleting symlink', path)
                os.remove(path)

        # Copy files into place.
        cmd = 'rsync -Rarv %s/./{%s} %s' % (basedir, ','.join(allfns), destdir)
        #print(cmd)
        print('Rsyncing: rsync -Rarv %s/./{[files]} %s' % (basedir, destdir))
        rtn = os.system(cmd)
        assert(rtn == 0)

        # Write updated checksum files.
        for path, chksum in new_checksum_files:
            if os.path.islink(path):
                print('Deleting symlink', path)
            print('writing checksum', path)
            with open(path + '.new', 'w') as f:
                f.write(chksum)
            os.rename(path + '.new', path)

            # Check new checksums -- expensive for, eg, tractor/001 !
            # dirnm = os.path.dirname(path)
            # cmd = 'cd %s && sha256sum --quiet -c %s' % (dirnm, os.path.basename(path))
            # print(cmd)
            # rtn = os.system(cmd)
            # assert(rtn == 0)
        #break

if __name__ == '__main__':
    main()
