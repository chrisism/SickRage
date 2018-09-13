# coding=utf-8
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: https://sickrage.github.io
# Git: https://github.com/SickRage/SickRage
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage. If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import datetime

from wakeonlan import send_magic_packet
from requests.compat import urljoin

import sickbeard
from sickbeard import helpers, logger

session = helpers.make_session()


def sendNZB(nzb):  # pylint:disable=too-many-return-statements, too-many-branches, too-many-statements
    '''
    Sends an NZB to SABnzbd via the API.

    :param nzb: The NZBSearchResult object to send to SAB
    '''

    category = sickbeard.SAB_CATEGORY
    if nzb.show.is_anime:
        category = sickbeard.SAB_CATEGORY_ANIME

    # if it aired more than 7 days ago, override with the backlog category IDs
    for curEp in nzb.episodes:
        if datetime.date.today() - curEp.airdate > datetime.timedelta(days=7):
            category = sickbeard.SAB_CATEGORY_ANIME_BACKLOG if nzb.show.is_anime else sickbeard.SAB_CATEGORY_BACKLOG

    # wake on lan?
    if not _is_downloader_awake(False):
        _wake()

    # set up a dict with the URL params in it
    params = {'output': 'json'}
    if sickbeard.SAB_USERNAME:
        params['ma_username'] = sickbeard.SAB_USERNAME
    if sickbeard.SAB_PASSWORD:
        params['ma_password'] = sickbeard.SAB_PASSWORD
    if sickbeard.SAB_APIKEY:
        params['apikey'] = sickbeard.SAB_APIKEY

    if category:
        params['cat'] = category

    if nzb.priority:
        params['priority'] = 2 if sickbeard.SAB_FORCED else 1

    logger.log('Sending NZB to SABnzbd')
    url = urljoin(sickbeard.SAB_HOST, 'api')

    if nzb.resultType == 'nzb':
        params['mode'] = 'addurl'
        params['name'] = nzb.url
        jdata = helpers.getURL(url, params=params, session=session, returns='json', verify=False)
    elif nzb.resultType == 'nzbdata':
        params['mode'] = 'addfile'
        multiPartParams = {'nzbfile': (nzb.name + '.nzb', nzb.extraInfo[0])}
        jdata = helpers.getURL(url, params=params, file=multiPartParams, session=session, returns='json', verify=False)

    if not jdata:
        logger.log('Error connecting to sab, no data returned')
        return False

    logger.log('Result text from SAB: {0}'.format(jdata), logger.DEBUG)

    result, error_ = _checkSabResponse(jdata)
    return result


def _checkSabResponse(jdata):
    '''
    Check response from SAB

    :param jdata: Response from requests api call
    :return: a list of (Boolean, string) which is True if SAB is not reporting an error
    '''
    if 'error' in jdata:
        logger.log(jdata['error'], logger.ERROR)
        return False, jdata['error']
    else:
        return True, jdata


def getSabAccesMethod(host=None):
    '''
    Find out how we should connect to SAB

    :param host: hostname where SAB lives
    :param username: username to use
    :param password: password to use
    :param apikey: apikey to use
    :return: (boolean, string) with True if method was successful
    '''
    params = {'mode': 'auth', 'output': 'json'}
    url = urljoin(host, 'api')
    data = helpers.getURL(url, params=params, session=session, returns='json', verify=False)
    if not data:
        return False, data

    return _checkSabResponse(data)


def testAuthentication(host=None, username=None, password=None, apikey=None):
    '''
    Sends a simple API request to SAB to determine if the given connection information is connect

    :param host: The host where SAB is running (incl port)
    :param username: The username to use for the HTTP request
    :param password: The password to use for the HTTP request
    :param apikey: The API key to provide to SAB
    :return: A tuple containing the success boolean and a message
    '''

    # build up the URL parameters
    params = {
        'mode': 'queue',
        'output': 'json',
        'ma_username': username,
        'ma_password': password,
        'apikey': apikey
    }

    url = urljoin(host, 'api')

    data = helpers.getURL(url, params=params, session=session, returns='json', verify=False)
    if not data:
        return False, data

    # check the result and determine if it's good or not
    result, sabText = _checkSabResponse(data)
    if not result:
        return False, sabText

    return True, 'Success'

def _is_downloader_awake(timeout = True):
    
    if sickbeard.WAIT_ENABLED:

        service_ip      = sickbeard.WAIT_IP_ADDRESS
        service_port    = sickbeard.WAIT_PORT
        service_timeout = sickbeard.WAIT_TIMEOUT

        if not timeout:
            service_timeout = 1

        logger.log('Checking if service is available @{}:{}.'.format(service_ip, service_port), logger.DEBUG)
        online = wait_net_service(service_ip, service_port, service_timeout)
        logger.log('Service {}:{} available? {}'.format(service_ip, service_port, online), logger.INFO)
        return online
        
    elif sickbeard.WAKE_ENABLED:
        return False

    log.debug('Skipping service availability check.')
    return True
        
def _wake():
    mac_address = sickrage.WAKE_MAC_ADDRESS
    logger.log('Waking machine before download with mac address "{}"'.format(mac_address), logger.DEBUG)
    send_magic_packet(mac_address)

    if sickbeard.WAIT_ENABLED and not _is_downloader_awake():
        logger.log('Wake on download failed.', logger.WARNING)

def wait_net_service(server, port, timeout=None):
    """ Wait for network service to appear 
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                    throw unhandled network exception
    """
    import socket
    import errno

    s = socket.socket()
    if timeout:
        from time import time as now
        # time module is needed to calc timeout shared between two exceptions
        end = now() + timeout

    while True:
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
                    s.settimeout(next_timeout)
            
            s.connect((server, port))
        
        except socket.timeout, err:
            # this exception occurs only if timeout is set
            if timeout:
                return False
      
        except socket.error, err:
            # catch timeout exception from underlying network library
            # this one is different from socket.timeout
            if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                logger.log('Wait for service error: {0}'.format(err), logger.ERROR)
                raise
        else:
            s.close()
            return True
