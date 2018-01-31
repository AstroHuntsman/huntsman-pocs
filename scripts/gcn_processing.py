#!/usr/bin/env python

import tempfile
import shutil
import sys
import glob

import gcn
import gcn.handlers
import gcn.notice_types

import astropy.coordinates
import astropy.time
import astropy.units as u

import healpy as hp
import numpy as np

import requests

from pocs.utils.too.parsers.grav_wave_parser import GravWaveParse
from pocs.utils.config import load_config


def get_skymap(skymap_url, save_file=False):
    """
    Download sky map, and parse FITS file.
    """
    # Send HTTP request for sky map
    response = requests.get(skymap_url, stream=True)

    # Raise an exception unless the download succeeded (HTTP 200 OK)
    response.raise_for_status()

    # Create a temporary file to store the downloaded FITS file
    with tempfile.NamedTemporaryFile() as tmpfile:
        # Save the FITS file to the temporary file
        shutil.copyfileobj(response.raw, tmpfile)
        tmpfile.flush()

        if save_file:
            # Save FITS payload to file
            shutil.copyfileobj(reponse.raw, open('{}.fits.gz'.format(tmpfile.name), 'wb'))

        # Read HEALPix data from the temporary file
        skymap, header = hp.read_map(tmpfile.name, h=True, verbose=False)
        header = dict(header)

    return skymap, header


def prob_observable(skymap, header):
    """
    Determine the integrated probability contained in a gravitational-wave
    sky map that is observable from a particular ground-based site at a
    particular time.
    """
    config_loc = load_config(config_files=[
        '{}/huntsman.yaml'.format(huntsman_config_dir)
    ])

    longitude = config_loc['location']['longitude']
    latitude = config_loc['location']['latitude']
    elevation = config_loc['location']['elevation']
    twilight_horizon = config_loc['location']['twilight_horizon']

    time = astropy.time.Time.now()

    # Determine resolution of sky map
    npix = len(skymap)
    nside = hp.npix2nside(npix)

    # Geodetic coordinates of observatory
    observatory = astropy.coordinates.EarthLocation(
        lat=latitude*u.deg, lon=longitude*u.deg, height=elevation*u.m)

    # Alt/az reference frame at observatory, now
    frame = astropy.coordinates.AltAz(obstime=time, location=observatory)

    # Look up (celestial) spherical polar coordinates of HEALPix grid.
    theta, phi = hp.pix2ang(nside, np.arange(npix))
    # Convert to RA, Dec.
    radecs = astropy.coordinates.SkyCoord(
        ra=phi*u.rad, dec=(0.5*np.pi - theta)*u.rad)

    # Transform grid to alt/az coordinates at observatory, now
    altaz = radecs.transform_to(frame)

    # Where is the sun, now
    sun_altaz = astropy.coordinates.get_sun(time).transform_to(altaz)

    airmass = 2.5 # Secant of zenith angle approximation
    prob = skymap[(sun_altaz.alt <= twilight_horizon*u.deg) & (altaz.secz <= airmass)].sum()

    return prob


# Function to call every time a GCN is received.
# Run only for notices of type LVC_INITIAL or LVC_UPDATE.
@gcn.handlers.include_notice_types(
    gcn.notice_types.LVC_INITIAL,
    gcn.notice_types.LVC_UPDATE)
def process_gcn(payload, root, configname='parsers_config'):
    config = load_config(configname)

    save_file = kwargs.get('save_file', False)
    verbose = kwargs.get('verbose', False)
    event = kwargs.get('event', None)

    if verbose:
        print('Got VOEvent:')
        print(payload)

    if root.attrib['role'] != 'observation': return

    if root.find("./What/Param[@name='Group']").attrib['value'] != event: return

    skymap_url = root.find(
        "./What/Param[@name='SKYMAP_URL_FITS_BASIC']").attrib['value']
    notice_type = root.find(
        "./What/Param[@name='AlertType']").attrib['value']
    name = root.find(
        "./What/Param[@name='GraceID']").attrib['value']

    if save_file:
        open('{}.xml'.format(name), 'w').write(payload)

    skymap, header = get_skymap(skymap_url, save_file)
    prob = prob_observable(skymap, header)

    header['NOTICE'] = notice_type

    if verbose:
        print('Source has a %d%% chance of being observable now' % round(100 * prob))
    if prob > 0.5:
        pass GravWaveParse().parse_event(header, skymap)


# Listen for GCNs until the program is interrupted.
gcn.listen(port=8096, handler=process_gcn)
