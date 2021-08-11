"""Integration tests for covidcast's CSV-to-database uploading."""

# standard library
from datetime import date
import os
import unittest
from unittest.mock import MagicMock

# third party
import mysql.connector

# first party
from delphi_utils import Nans
from delphi.epidata.client.delphi_epidata import Epidata
from delphi.epidata.acquisition.covidcast.csv_to_database import main
import delphi.operations.secrets as secrets

# py3tester coverage target (equivalent to `import *`)
__test_target__ = 'delphi.epidata.acquisition.covidcast.csv_to_database'


class CsvUploadingTests(unittest.TestCase):
  """Tests covidcast CSV uploading."""

  def setUp(self):
    """Perform per-test setup."""

    # connect to the `epidata` database and clear the datapoint and data_reference tables
    cnx = mysql.connector.connect(
        user='user',
        password='pass',
        host='delphi_database_epidata',
        database='epidata')
    cur = cnx.cursor()
    cur.execute('SET foreign_key_checks = 0')
    cur.execute('truncate table datapoint')
    cur.execute('truncate table data_reference')
    cur.execute('SET foreign_key_checks = 1')
    cnx.commit()
    cur.close()

    # make connection and cursor available to test cases
    self.cnx = cnx
    self.cur = cnx.cursor()

    # use the local instance of the epidata database
    secrets.db.host = 'delphi_database_epidata'
    secrets.db.epi = ('user', 'pass')

    # use the local instance of the Epidata API
    Epidata.BASE_URL = 'http://delphi_web_epidata/epidata/api.php'

  def tearDown(self):
    """Perform per-test teardown."""
    self.cur.close()
    self.cnx.close()

  def test_uploading(self):
    """Scan, parse, upload, archive, serve, and fetch a covidcast signal."""

    # print full diff if something unexpected comes out
    self.maxDiff=None

    # make some fake data files
    data_dir = 'covid/data'
    source_receiving_dir = data_dir + '/receiving/src-name'
    log_file_directory = "/var/log/"
    os.makedirs(source_receiving_dir, exist_ok=True)
    os.makedirs(log_file_directory, exist_ok=True)

    # valid
    with open(source_receiving_dir + '/20200419_state_test.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'ca,1,0.1,10,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')
      f.write(f'tx,2,0.2,20,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')
      f.write(f'fl,3,0.3,30,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # valid, old style no missing cols should have intelligent defaults
    with open(source_receiving_dir + '/20200419_state_test_no_missing.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size\n')
      f.write('ca,1,0.1,10\n')
      f.write('tx,NA,0.2,20\n')
      f.write('wa,3,0.3,30\n')

    # invalid, missing with an inf value
    with open(source_receiving_dir + '/20200419_state_test_missing1.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'fl,inf,0.3,30,{Nans.OTHER},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # invalid, missing with an incorrect missing code
    with open(source_receiving_dir + '/20200419_state_test_missing2.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'tx,NA,0.2,20,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # invalid, no missing with an incorrect missing code
    with open(source_receiving_dir + '/20200419_state_test_missing3.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'wa,3,0.3,30,{Nans.OTHER},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # valid wip
    with open(source_receiving_dir + '/20200419_state_wip_prototype.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'me,10,0.01,100,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')
      f.write(f'nd,20,0.02,200,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')
      f.write(f'wa,30,0.03,300,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # invalid
    with open(source_receiving_dir + '/20200419_state_wip_really_long_name_that_will_be_accepted.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'pa,100,5.4,624,{Nans.NOT_MISSING},{Nans.NOT_MISSING},{Nans.NOT_MISSING}\n')

    # invalid
    with open(source_receiving_dir + '/20200419_state_wip_really_long_name_that_will_get_truncated_lorem_ipsum_dolor_sit_amet.csv', 'w') as f:
      f.write('geo_id,val,se,sample_size,missing_val,missing_se,missing_sample_size\n')
      f.write(f'pa,100,5.4,624,{Nans.NOT_MISSING}, {Nans.NOT_MISSING}, {Nans.NOT_MISSING}\n')

    # invalid
    with open(source_receiving_dir + '/20200420_state_test.csv', 'w') as f:
      f.write('this,header,is,wrong\n')

    # invalid
    with open(source_receiving_dir + '/hello.csv', 'w') as f:
      f.write('file name is wrong\n')

    # upload CSVs
    # TODO: use an actual argparse object for the args instead of a MagicMock
    args = MagicMock(
        log_file=log_file_directory +
        "output.log",
        data_dir=data_dir,
        is_wip_override=False,
        not_wip_override=False,
        specific_issue_date=False)
    main(args)

    # request CSV data from the API
    response = Epidata.covidcast(
        'src-name', 'test', 'day', 'state', 20200419, '*')


    expected_issue_day=date.today()
    expected_issue=expected_issue_day.strftime("%Y%m%d")
    def apply_lag(expected_epidata):
      for dct in expected_epidata:
        dct['issue'] = int(expected_issue)
        time_value_day = date(year=dct['time_value'] // 10000,
                              month=dct['time_value'] % 10000 // 100,
                              day= dct['time_value'] % 100)
        expected_lag = (expected_issue_day - time_value_day).days
        dct['lag'] = expected_lag
      return expected_epidata

    # verify data matches the CSV
    # NB these are ordered by geo_value
    self.assertEqual(response, {
      'result': 1,
      'epidata': apply_lag([
        {
          'time_value': 20200419,
          'geo_value': 'ca',
          'value': 1,
          'stderr': 0.1,
          'sample_size': 10,
          'direction': None,
          'signal': 'test',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'fl',
          'value': 3,
          'stderr': 0.3,
          'sample_size': 30,
          'direction': None,
          'signal': 'test',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'tx',
          'value': 2,
          'stderr': 0.2,
          'sample_size': 20,
          'direction': None,
          'signal': 'test',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
    ]),
      'message': 'success',
    })

    # request CSV data from the API on the test with missing values
    response = Epidata.covidcast(
      'src-name', 'test_no_missing', 'day', 'state', 20200419, '*')

    # verify data matches the CSV
    # NB these are ordered by geo_value
    self.assertEqual(response, {
      'result': 1,
      'epidata': apply_lag([
        {
          'time_value': 20200419,
          'geo_value': 'ca',
          'value': 1,
          'stderr': 0.1,
          'sample_size': 10,
          'direction': None,
          'signal': 'test_no_missing',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'tx',
          'value': None,
          'stderr': 0.2,
          'sample_size': 20,
          'direction': None,
          'signal': 'test_no_missing',
          'missing_value': Nans.OTHER,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'wa',
          'value': 3,
          'stderr': 0.3,
          'sample_size': 30,
          'direction': None,
          'signal': 'test_no_missing',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
       ]),
      'message': 'success',
    })

    # invalid missing files
    response = Epidata.covidcast(
      'src-name', 'test_missing1', 'day', 'state', 20200419, '*')
    self.assertEqual(response, {
      'result': -2,
      'message': 'no results',
    })
    response = Epidata.covidcast(
      'src-name', 'test_missing2', 'day', 'state', 20200419, '*')
    self.assertEqual(response, {
      'result': -2,
      'message': 'no results',
    })
    response = Epidata.covidcast(
      'src-name', 'test_missing3', 'day', 'state', 20200419, '*')
    self.assertEqual(response, {
      'result': -2,
      'message': 'no results',
    })

    # request CSV data from the API on WIP signal
    response = Epidata.covidcast(
      'src-name', 'wip_prototype', 'day', 'state', 20200419, '*')

    # verify data matches the CSV
    # NB these are ordered by geo_value
    self.assertEqual(response, {
      'result': 1,
      'epidata': apply_lag([
        {
          'time_value': 20200419,
          'geo_value': 'me',
          'value': 10,
          'stderr': 0.01,
          'sample_size': 100,
          'direction': None,
          'signal': 'wip_prototype',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'nd',
          'value': 20,
          'stderr': 0.02,
          'sample_size': 200,
          'direction': None,
          'signal': 'wip_prototype',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
        {
          'time_value': 20200419,
          'geo_value': 'wa',
          'value': 30,
          'stderr': 0.03,
          'sample_size': 300,
          'direction': None,
          'signal': 'wip_prototype',
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
       ]),
      'message': 'success',
    })

    # request CSV data from the API on the signal with name length 32<x<64
    response = Epidata.covidcast(
      'src-name', 'wip_really_long_name_that_will_be_accepted', 'day', 'state', 20200419, '*')

    # verify data matches the CSV
    self.assertEqual(response, {
      'result': 1,
      'message': 'success',
      'epidata': apply_lag([
        {
          'time_value': 20200419,
          'geo_value': 'pa',
          'value': 100,
          'stderr': 5.4,
          'sample_size': 624,
          'direction': None,
          'signal': 'wip_really_long_name_that_will_be_accepted',\
          'missing_value': Nans.NOT_MISSING,
          'missing_stderr': Nans.NOT_MISSING,
          'missing_sample_size': Nans.NOT_MISSING,
        },
      ])
    })

    # request CSV data from the API on the long-named signal
    response = Epidata.covidcast(
      'src-name', 'wip_really_long_name_that_will_get_truncated_lorem_ipsum_dolor_s', 'day', 'state', 20200419, '*')

    # verify data matches the CSV
    # if the CSV failed correctly there should be no results
    self.assertEqual(response, {
      'result': -2,
      'message': 'no results',
    })

    # verify timestamps and default values are reasonable
    self.cur.execute('select value_updated_timestamp, direction_updated_timestamp, direction from covidcast')
    for value_updated_timestamp, direction_updated_timestamp, direction in self.cur:
      self.assertGreater(value_updated_timestamp, 0)
      self.assertEqual(direction_updated_timestamp, 0)
      self.assertIsNone(direction)

    # verify that the CSVs were archived
    for sig in ["test","wip_prototype"]:
      path = data_dir + f'/archive/successful/src-name/20200419_state_{sig}.csv.gz'
      self.assertIsNotNone(os.stat(path))
    path = data_dir + '/archive/failed/src-name/20200420_state_test.csv'
    self.assertIsNotNone(os.stat(path))
    path = data_dir + '/archive/failed/unknown/hello.csv'
    self.assertIsNotNone(os.stat(path))
