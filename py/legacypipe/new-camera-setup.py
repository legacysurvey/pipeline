import os
import sys
import logging

from legacypipe.survey import LegacySurveyData

logger = logging.getLogger('legacypipe.new-camera-setup')
def info(*args):
    from legacypipe.utils import log_info
    log_info(logger, args)
def debug(*args):
    from legacypipe.utils import log_debug
    log_debug(logger, args)


def main():
    from legacyzpts.legacy_zeropoints import CAMERAS

    
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument('--camera', required=True)

    parser.add_argument('--image-hdu', default=0, type=int, help='Read image data from the given HDU number')

    parser.add_argument('--survey-dir', type=str, default=None,
                        help='Override the $LEGACY_SURVEY_DIR environment variable')
    parser.add_argument('--verbose', '-v', action='store_true', default=False, help='More logging')

    parser.add_argument('image', metavar='image-filename', help='Image filename to read')

    opt = parser.parse_args()

    if opt.verbose:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO
    logging.basicConfig(level=lvl, format='%(message)s', stream=sys.stdout)
    # tractor logging is *soooo* chatty
    logging.getLogger('tractor.engine').setLevel(lvl + 10)

    if not opt.camera in CAMERAS:
        print('You must add your new camera to the list of known cameras at the top of the legacy_zeropoints.py script -- the CAMERAS variable.')
        return

    survey = LegacySurveyData(survey_dir=opt.survey_dir)

    clazz = None
    try:
        clazz = survey.image_class_for_camera(opt.camera)
    except KeyError:
        print('You must:')
        print(' - create a new legacypipe.image.LegacySurveyImage subclass for your new camera')
        print(' - add it to the dict in legacypipe/survey.py : LegacySurveyData : self.image_typemap')
        print(' - import your new class in LegacySurveyData.__init__().')
        return

    info('For camera "%s", found LegacySurveyImage subclass: %s' % (opt.camera, str(clazz)))
    
    info('Reading', opt.image, 'and trying to create new image object...')

    img = survey.get_image_object(None, camera=opt.camera,
                                  image_fn=opt.image, image_hdu=opt.image_hdu,
                                  camera_setup=True)
                                  
    info('Got image of type', type(img))

    # Here we're copying some code out of image.py...
    image_fn = opt.image
    image_hdu = opt.image_hdu
    img.image_filename = image_fn
    img.imgfn = os.path.join(img.survey.get_image_dir(), image_fn)

    info('Relative path to image file -- will be stored in the survey-ccds file --: ', img.image_filename)
    info('Filesystem path to image file:', img.imgfn)

    if not os.path.exists(img.imgfn):
        print('Filesystem path does not exist.  Should be survey-dir path + images (%s) + image-file-argument (%s)' % (survey.get_image_dir(), image_fn))
        return

    info('Reading primary FITS header from image file...')
    primhdr = img.read_image_primary_header()

    info('Reading a bunch of metadata from image primary header:')

    for k in ['band', 'propid', 'expnum', 'camera', 'exptime']:
        info('get_%s():' % k)
        v = getattr(img, 'get_'+k)(primhdr)
        info('  -> "%s"' % v)
        setattr(img, k, v)

    info('get_mjd():')
    img.mjdobs = img.get_mjd(primhdr)
    info('  -> "%s"' % img.mjdobs)

    namechange = {'date': 'procdate',}
    for key in ['HA', 'DATE', 'OBJECT', 'PLVER', 'PLPROCID']:
        info('get "%s" from primary header.' % key)
        val = primhdr.get(key)
        if isinstance(val, str):
            val = val.strip()
            if len(val) == 0:
                raise ValueError('Empty header card: %s' % key)
        key = namechange.get(key.lower(), key.lower())
        key = key.replace('-', '_')
        info('  -> "%s"' % val)
        setattr(img, key, val)

    img.hdu = image_hdu
    info('Will read image header from HDU', image_hdu)
    hdr = img.read_image_header(ext=image_hdu)
    info('Reading image metadata...')
    hinfo = img.read_image_fits()[image_hdu].get_info()
    #info('Got:', hinfo)
    img.height,img.width = hinfo['dims']
    info('Got image size', img.width, 'x', img.height, 'pixels')
    img.hdu = hinfo['hdunum'] - 1
    for key in ['ccdname', 'pixscale', 'fwhm']:
        info('get_%s():' % key)
        v = getattr(img, 'get_'+key)(primhdr, hdr)
        info('  -> "%s"' % v)
        setattr(img, key, v)

    for k,d in [('dq_hdu',img.hdu), ('wt_hdu',img.hdu), ('sig1',0.), ('ccdzpt',0.),
                ('dradec',(0.,0.))]:
        v = getattr(img, k, d)
        setattr(img, k, v)

    img.compute_filenames()
    info('Will read image pixels from file        ', img.imgfn, 'HDU', img.hdu)
    info('Will read inverse-variance map from file', img.wtfn,  'HDU', img.wt_hdu)
    info('Will read data-quality map from file    ', img.dqfn,  'HDU', img.dq_hdu)

    info('Will read images from these FITS HDUs:', img.get_extension_list())

    # test funpack_files?

    info('Source Extractor & PsfEx will read the following config files:')
    sedir = survey.get_se_dir()
    for (type, suff) in [('SE config', '.se'),
                         ('SE params', '.param'),
                         ('SE convolution filter', '.conv'),
                         ('PsfEx config', '.psfex'),
                         ]:
        fn = os.path.join(sedir, img.camera + suff)
        ex = os.path.exists(fn)
        info('  %s: %s (%s)' % (type, fn, 'exists' if ex else 'does not exist'))

    info('Special PsfEx flags for this CCD:', survey.get_psfex_conf(img.camera, img.expnum, img.ccdname))

    # Once legacy_zeropoints.py starts...
    ra_bore, dec_bore = img.get_radec_bore(primhdr)
    info('RA,Dec boresight:', ra_bore, dec_bore)
    info('Airmass:', img.get_airmass(primhdr, hdr, ra_bore, dec_bore))
    info('Gain:', img.get_gain(primhdr, hdr))
    info('WCS Reference pixel CRPIX[12]:', hdr['CRPIX1'], hdr['CRPIX2'])
    info('WCS Reference pos CRVAL[12]:', hdr['CRVAL1'], hdr['CRVAL2'])
    info('WCS CD matrix:', img.get_cd_matrix(primhdr, hdr))

    wcs = img.get_wcs(hdr=hdr)
    info('Got WCS object:', wcs)

    H = img.height
    W = img.width
    ccdra, ccddec = wcs.pixelxy2radec((W+1) / 2.0, (H+1) / 2.0)
    info('With image size %i x %i, central RA,Dec is (%.4f, %.4f)' %
         (W, H, ccdra, ccddec))

    slc = img.get_good_image_slice(None)
    info('Good region in this image (slice):', slc)

    # PsfEx file?  FWHM?

    # Reading data...
    info('Reading data quality / mask file...')
    dq,dqhdr = img.read_dq(header=True, slc=slc)
    info('DQ file:', dq.shape, dq.dtype, 'min:', dq.min(), 'max', dq.max(),
         'number of pixels == 0:', np.sum(dq == 0))
    if dq is not None:
        info('Remapping data quality / mask file...')
        dq = img.remap_dq(dq, dqhdr)
    if dq is None:
        info('No DQ file')
    else:
        info('DQ file:', dq.shape, dq.dtype, 'min:', dq.min(), 'max', dq.max(),
             'number of pixels == 0:', np.sum(dq == 0))

    info('Reading inverse-variance / weight file...')
    invvar = img.read_invvar(dq=dq, slc=slc)
    info('Invvar map:', invvar.shape, invvar.dtype, 'min:', invvar.min(),
         'max', invvar.max(), 'median', invvar.median(),
         'number of pixels == 0:', np.sum(invvar == 0), ', number >0:', np.sum(invvar>0))
    info('Reading image file...')
    impix = img.read_image(slc=slc)
    info('Image pixels:', impix.shape, impix.dtype, 'min:', impix.min(),
         'max', impix.max(), 'median', np.median(impix.ravel()))
    info('Running fix_saturation...')
    img.fix_saturation(impix, dq, invvar, primhdr, hdr, slc)
    info('Image pixels:', impix.shape, impix.dtype, 'min:', impix.min(),
         'max', impix.max(), 'median', np.median(impix.ravel()))
    info('Invvar map:', invvar.shape, invvar.dtype, 'min:', invvar.min(),
         'max', invvar.max(), 'median', invvar.median(),
         'number of pixels == 0:', np.sum(invvar == 0), ', number >0:', np.sum(invvar>0))
    info('DQ file:', dq.shape, dq.dtype, 'min:', dq.min(), 'max', dq.max(),
         'number of pixels == 0:', np.sum(dq == 0))

    info('Calling estimate_sig1()...')
    img.sig1 = img.estimate_sig1(impix, invvar, dq, primhdr, hdr)
    info('Got sig1 =', img.sig1)

    info('Calling remap_invvar...')
    invvar = img.remap_invvar(invvar, primhdr, impix, dq)
    info('Blanking out', np.sum((invvar == 0) * (impix != 0)), 'image pixels with invvar=0')
    impix[invvar == 0] = 0.

    info('Image pixels:', impix.shape, impix.dtype, 'min:', impix.min(),
         'max', impix.max(), 'median', np.median(impix.ravel()))
    info('Invvar map:', invvar.shape, invvar.dtype, 'min:', invvar.min(),
         'max', invvar.max(), 'median', invvar.median(),
         'number of pixels == 0:', np.sum(invvar == 0), ', number >0:', np.sum(invvar>0))
    info('DQ file:', dq.shape, dq.dtype, 'min:', dq.min(), 'max', dq.max(),
         'number of pixels == 0:', np.sum(dq == 0))

    info('Scaling weight(invvar) and image pixels...')
    invvar = img.scale_weight(invvar)
    impix = img.scale_image(impix)
    info('Image pixels:', impix.shape, impix.dtype, 'min:', impix.min(),
         'max', impix.max(), 'median', np.median(impix.ravel()))
    info('Invvar map:', invvar.shape, invvar.dtype, 'min:', invvar.min(),
         'max', invvar.max(), 'median', invvar.median(),
         'number of pixels == 0:', np.sum(invvar == 0), ', number >0:', np.sum(invvar>0))

    info('Estimating sky level...')
    sky_img, skymed, skyrms = img.estimate_sky(impix, invvar, dq, primhdr, hdr)
    zp0 = img.nominal_zeropoint(img.band)
    info('Got nominal zeropoint for band', img.band, ':', zp0)
    skybr = zp0 - 2.5*np.log10(skymed / img.pixscale / img.pixscale / img.exptime)
    info('Sky level: %.2f count/pix' % skymed)
    info('Sky brightness: %.3f mag/arcsec^2 (assuming nominal zeropoint)' % skybr)

    zpt = img.get_zeropoint(primhdr, hdr)
    info('Does a zeropoint already exist in the image headers?  zpt=', zpt)

if __name__ == '__main__':
    main()
