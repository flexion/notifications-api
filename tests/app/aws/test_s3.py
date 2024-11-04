import os
from datetime import timedelta
from os import getenv
from unittest.mock import ANY, MagicMock, Mock, call, patch

import botocore
import pytest
from botocore.exceptions import ClientError

from app.aws.s3 import (
    cleanup_old_s3_objects,
    download_from_s3,
    file_exists,
    get_job_and_metadata_from_s3,
    get_job_from_s3,
    get_job_id_from_s3_object_key,
    get_personalisation_from_s3,
    get_phone_number_from_s3,
    get_s3_client,
    get_s3_file,
    get_s3_files,
    get_s3_object,
    get_s3_resource,
    list_s3_objects,
    read_s3_file,
    remove_csv_object,
    remove_s3_object,
)
from app.clients import AWS_CLIENT_CONFIG
from app.utils import utc_now
from notifications_utils import aware_utcnow

default_access_key = getenv("CSV_AWS_ACCESS_KEY_ID")
default_secret_key = getenv("CSV_AWS_SECRET_ACCESS_KEY")
default_region = getenv("CSV_AWS_REGION")


def single_s3_object_stub(key="foo", last_modified=None):
    return {
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
        "Key": key,
        "LastModified": last_modified or utc_now(),
    }


def test_cleanup_old_s3_objects(mocker):
    """
    Currently we are going to delete s3 objects if they are more than 14 days old,
    because we want to delete all jobs older than 7 days, and jobs can be scheduled
    three days in advance, and on top of that we want to leave a little cushion for
    the time being.  This test shows that a 3 day old job ("B") is not deleted,
    whereas a 30 day old job ("A") is.
    """
    mocker.patch("app.aws.s3.get_bucket_name", return_value="Bucket")

    mock_s3_client = mocker.Mock()
    mocker.patch("app.aws.s3.get_s3_client", return_value=mock_s3_client)
    mock_remove_csv_object = mocker.patch("app.aws.s3.remove_csv_object")
    lastmod30 = aware_utcnow() - timedelta(days=30)
    lastmod3 = aware_utcnow() - timedelta(days=3)

    mock_s3_client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "A", "LastModified": lastmod30},
            {"Key": "B", "LastModified": lastmod3},
        ]
    }
    cleanup_old_s3_objects()
    mock_s3_client.list_objects_v2.assert_called_with(Bucket="Bucket")
    mock_remove_csv_object.assert_called_once_with("A")


def test_read_s3_file_success(mocker):
    mock_s3res = MagicMock()
    mock_extract_personalisation = mocker.patch("app.aws.s3.extract_personalisation")
    mock_extract_phones = mocker.patch("app.aws.s3.extract_phones")
    mock_set_job_cache = mocker.patch("app.aws.s3.set_job_cache")
    mock_get_job_id = mocker.patch("app.aws.s3.get_job_id_from_s3_object_key")
    bucket_name = "test_bucket"
    object_key = "test_object_key"
    job_id = "12345"
    file_content = "some file content"
    mock_get_job_id.return_value = job_id
    mock_s3_object = MagicMock()
    mock_s3_object.get.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=file_content.encode("utf-8")))
    }
    mock_s3res.Object.return_value = mock_s3_object
    mock_extract_phones.return_value = ["1234567890"]
    mock_extract_personalisation.return_value = {"name": "John Doe"}

    global job_cache
    job_cache = {}

    read_s3_file(bucket_name, object_key, mock_s3res)
    mock_get_job_id.assert_called_once_with(object_key)
    mock_s3res.Object.assert_called_once_with(bucket_name, object_key)
    expected_calls = [
        call(ANY, job_id, file_content),
        call(ANY, f"{job_id}_phones", ["1234567890"]),
        call(ANY, f"{job_id}_personalisation", {"name": "John Doe"}),
    ]
    mock_set_job_cache.assert_has_calls(expected_calls, any_order=True)


def test_download_from_s3_success(mocker):
    mock_s3 = MagicMock()
    mock_get_s3_client = mocker.patch("app.aws.s3.get_s3_client")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    mock_logger = mock_current_app.logger
    mock_get_s3_client.return_value = mock_s3
    bucket_name = "test_bucket"
    s3_key = "test_key"
    local_filename = "test_file"
    access_key = "access_key"
    region = "test_region"
    download_from_s3(
        bucket_name, s3_key, local_filename, access_key, "secret_key", region
    )
    mock_s3.download_file.assert_called_once_with(bucket_name, s3_key, local_filename)
    mock_logger.info.assert_called_once_with(
        f"File downloaded successfully to {local_filename}"
    )


def test_download_from_s3_no_credentials_error(mocker):
    mock_get_s3_client = mocker.patch("app.aws.s3.get_s3_client")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    mock_logger = mock_current_app.logger
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = botocore.exceptions.NoCredentialsError
    mock_get_s3_client.return_value = mock_s3
    try:
        download_from_s3(
            "test_bucket", "test_key", "test_file", "access_key", "secret_key", "region"
        )
    except Exception:
        pass
    mock_logger.exception.assert_called_once_with("Credentials not found")


def test_download_from_s3_general_exception(mocker):
    mock_get_s3_client = mocker.patch("app.aws.s3.get_s3_client")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    mock_logger = mock_current_app.logger
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = Exception()
    mock_get_s3_client.return_value = mock_s3
    try:
        download_from_s3(
            "test_bucket", "test_key", "test_file", "access_key", "secret_key", "region"
        )
    except Exception:
        pass
    mock_logger.exception.assert_called_once()


def test_list_s3_objects(mocker):
    mocker.patch("app.aws.s3._get_bucket_name", return_value="Foo")
    mock_s3_client = mocker.Mock()
    mocker.patch("app.aws.s3.get_s3_client", return_value=mock_s3_client)
    lastmod30 = aware_utcnow() - timedelta(days=30)
    lastmod3 = aware_utcnow() - timedelta(days=3)

    mock_s3_client.list_objects_v2.side_effect = [
        {
            "Contents": [
                {"Key": "A", "LastModified": lastmod30},
                {"Key": "B", "LastModified": lastmod3},
            ]
        }
    ]
    result = list_s3_objects()
    assert list(result) == ["B"]


def test_get_s3_file_makes_correct_call(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    get_s3_file(
        "foo-bucket",
        "bar-file.txt",
        default_access_key,
        default_secret_key,
        default_region,
    )

    get_s3_mock.assert_called_with(
        "foo-bucket",
        "bar-file.txt",
        default_access_key,
        default_secret_key,
        default_region,
    )


@pytest.mark.parametrize(
    "job, job_id, job_row_number, expected_phone_number",
    [
        ("phone number\r\n+15555555555", "aaa", 0, "15555555555"),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "bbb",
            1,
            "15552222222",
        ),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "ccc",
            0,
            "15551111111",
        ),
        (
            "Phone number,name,date,time,address,English,Spanish\r\n15553333333,Tim,10/16,2:00 PM,5678 Tom St.,no,yes",
            "ddd",
            0,
            "15553333333",
        ),
        (
            # simulate file saved with utf8withbom
            "\\ufeffPHONE NUMBER,Name\r\n5555555550,T 1\r\n5555555551,T 5,3/31/2024\r\n5555555552,T 2",
            "eee",
            2,
            "5555555552",
        ),
    ],
)
def test_get_phone_number_from_s3(
    mocker, job, job_id, job_row_number, expected_phone_number
):
    get_job_mock = mocker.patch("app.aws.s3.get_job_from_s3")
    get_job_mock.return_value = job
    phone_number = get_phone_number_from_s3("service_id", job_id, job_row_number)
    assert phone_number == expected_phone_number


@pytest.mark.parametrize(
    "key, expected_job_id",
    [
        ("service-blahblahblah-notify/abcde.csv", "abcde"),
        (
            "service-x-notify/4c99f361-4ed7-49b1-bd6f-02fe0c807c53.csv",
            "4c99f361-4ed7-49b1-bd6f-02fe0c807c53",
        ),
    ],
)
def test_get_job_id_from_s3_object_key(key, expected_job_id):
    actual_job_id = get_job_id_from_s3_object_key(key)
    assert actual_job_id == expected_job_id


def mock_s3_get_object_slowdown(*args, **kwargs):
    error_response = {
        "Error": {
            "Code": "SlowDown",
            "Message": "Reduce your request rate",
        }
    }
    raise ClientError(error_response, "GetObject")


def test_get_job_from_s3_exponential_backoff_on_throttling(mocker):
    # We try multiple times to retrieve the job, and if we can't we return None
    mock_get_object = mocker.patch(
        "app.aws.s3.get_s3_object", side_effect=mock_s3_get_object_slowdown
    )
    mocker.patch("app.aws.s3.file_exists", return_value=True)
    job = get_job_from_s3("service_id", "job_id")
    assert job is None
    assert mock_get_object.call_count == 8


def test_get_job_from_s3_exponential_backoff_on_random_exception(mocker):
    # We try multiple times to retrieve the job, and if we can't we return None
    mock_get_object = mocker.patch("app.aws.s3.get_s3_object", side_effect=Exception())
    mocker.patch("app.aws.s3.file_exists", return_value=True)
    job = get_job_from_s3("service_id", "job_id")
    assert job is None
    assert mock_get_object.call_count == 1


def test_get_job_from_s3_exponential_backoff_file_not_found(mocker):
    mock_get_object = mocker.patch("app.aws.s3.get_s3_object", return_value=None)
    mocker.patch("app.aws.s3.file_exists", return_value=False)
    job = get_job_from_s3("service_id", "job_id")
    assert job is None
    assert mock_get_object.call_count == 0


@pytest.mark.parametrize(
    "job, job_id, job_row_number, expected_personalisation",
    [
        ("phone number\r\n+15555555555", "aaa", 0, {"phone number": "+15555555555"}),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "bbb",
            1,
            {
                "day of week": "tuesday",
                "favorite color": "red",
                "phone number": "+1 (555) 222-2222",
            },
        ),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "ccc",
            0,
            {
                "day of week": "monday",
                "favorite color": "green",
                "phone number": "1.555.111.1111",
            },
        ),
    ],
)
def test_get_personalisation_from_s3(
    mocker, job, job_id, job_row_number, expected_personalisation
):
    get_job_mock = mocker.patch("app.aws.s3.get_job_from_s3")
    get_job_mock.return_value = job
    personalisation = get_personalisation_from_s3("service_id", job_id, job_row_number)
    assert personalisation == expected_personalisation


def test_remove_csv_object(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    remove_csv_object("mykey")

    get_s3_mock.assert_called_once_with(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )


def test_remove_csv_object_alternate(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    remove_s3_object(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )

    get_s3_mock.assert_called_once_with(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )


def test_file_exists_true(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")

    file_exists(
        "mykey",
    )
    get_s3_mock.assert_called_once()


def test_file_exists_false(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    error_response = {
        "Error": {"Code": 500, "Message": "bogus"},
        "ResponseMetadata": {"HTTPStatusCode": 500},
    }
    get_s3_mock.side_effect = ClientError(
        error_response=error_response, operation_name="bogus"
    )

    with pytest.raises(ClientError):
        file_exists(
            "mykey",
        )

    get_s3_mock.assert_called_once()


def test_get_s3_files_success(notify_api, mocker):
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    mock_current_app.config = {"CSV_UPLOAD_BUCKET": {"bucket": "test-bucket"}}
    mock_thread_pool_executor = mocker.patch("app.aws.s3.ThreadPoolExecutor")
    mock_read_s3_file = mocker.patch("app.aws.s3.read_s3_file")
    mock_list_s3_objects = mocker.patch("app.aws.s3.list_s3_objects")
    mock_get_s3_resource = mocker.patch("app.aws.s3.get_s3_resource")
    mock_list_s3_objects.return_value = ["file1.csv", "file2.csv"]
    mock_s3_resource = MagicMock()
    mock_get_s3_resource.return_value = mock_s3_resource
    mock_executor = MagicMock()

    def mock_map(func, iterable):
        for item in iterable:
            func(item)

    mock_executor.map.side_effect = mock_map
    mock_thread_pool_executor.return_value.__enter__.return_value = mock_executor

    get_s3_files()

    # mock_current_app.config.__getitem__.assert_called_once_with("CSV_UPLOAD_BUCKET")
    mock_list_s3_objects.assert_called_once()
    mock_thread_pool_executor.assert_called_once()

    mock_executor.map.assert_called_once()

    calls = [
        (("test-bucket", "file1.csv", mock_s3_resource),),
        (("test-bucket", "file2.csv", mock_s3_resource),),
    ]

    mock_read_s3_file.assert_has_calls(calls, any_order=True)

    # mock_current_app.info.assert_any_call("job_cache length before regen: 0 #notify-admin-1200")

    # mock_current_app.info.assert_any_call("job_cache length after regen: 0 #notify-admin-1200")


@patch("app.aws.s3.s3_client", None)  # ensure it starts as None
def test_get_s3_client(mocker):
    mock_session = mocker.patch("app.aws.s3.Session")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    sa_key = "sec"
    sa_key = f"{sa_key}ret_access_key"
    mock_current_app.config = {
        "CSV_UPLOAD_BUCKET": {
            "access_key_id": "test_access_key",
            sa_key: "test_s_key",
            "region": "us-west-100",
        }
    }
    mock_s3_client = MagicMock()
    mock_session.return_value.client.return_value = mock_s3_client
    result = get_s3_client()

    mock_session.return_value.client.assert_called_once_with("s3")
    assert result == mock_s3_client


@patch("app.aws.s3.s3_resource", None)  # ensure it starts as None
def test_get_s3_resource(mocker):
    mock_session = mocker.patch("app.aws.s3.Session")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    sa_key = "sec"
    sa_key = f"{sa_key}ret_access_key"

    mock_current_app.config = {
        "CSV_UPLOAD_BUCKET": {
            "access_key_id": "test_access_key",
            sa_key: "test_s_key",
            "region": "us-west-100",
        }
    }
    mock_s3_resource = MagicMock()
    mock_session.return_value.resource.return_value = mock_s3_resource
    result = get_s3_resource()

    mock_session.return_value.resource.assert_called_once_with(
        "s3", config=AWS_CLIENT_CONFIG
    )
    assert result == mock_s3_resource


def test_get_job_and_metadata_from_s3(mocker):
    mock_get_s3_object = mocker.patch("app.aws.s3.get_s3_object")
    mock_get_job_location = mocker.patch("app.aws.s3.get_job_location")

    mock_get_job_location.return_value = {"bucket_name", "new_key"}
    mock_s3_object = MagicMock()
    mock_s3_object.get.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"job data")),
        "Metadata": {"key": "value"},
    }
    mock_get_s3_object.return_value = mock_s3_object
    result = get_job_and_metadata_from_s3("service_id", "job_id")

    mock_get_job_location.assert_called_once_with("service_id", "job_id")
    # mock_get_s3_object.assert_called_once_with("bucket_name", "new_key")
    assert result == ("job data", {"key": "value"})


def test_get_job_and_metadata_from_s3_fallback_to_old_location(mocker):
    mock_get_job_location = mocker.patch("app.aws.s3.get_job_location")
    mock_get_old_job_location = mocker.patch("app.aws.s3.get_old_job_location")
    mock_get_job_location.return_value = {"bucket_name", "new_key"}
    mock_get_s3_object = mocker.patch("app.aws.s3.get_s3_object")
    # mock_get_s3_object.side_effect = [ClientError({"Error": {}}, "GetObject"), mock_s3_object]
    mock_get_old_job_location.return_value = {"bucket_name", "old_key"}
    mock_s3_object = MagicMock()
    mock_s3_object.get.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"old job data")),
        "Metadata": {"old_key": "old_value"},
    }
    mock_get_s3_object.side_effect = [
        ClientError({"Error": {}}, "GetObject"),
        mock_s3_object,
    ]
    result = get_job_and_metadata_from_s3("service_id", "job_id")
    mock_get_job_location.assert_called_once_with("service_id", "job_id")
    mock_get_old_job_location.assert_called_once_with("service_id", "job_id")
    # mock_get_s3_object.assert_any_call("bucket_name", "new_key")
    # mock_get_s3_object.assert_any_call("bucket_name", "old_key")
    assert result == ("old job data", {"old_key": "old_value"})


def test_get_s3_object_client_error(mocker):
    mock_get_s3_resource = mocker.patch("app.aws.s3.get_s3_resource")
    mock_current_app = mocker.patch("app.aws.s3.current_app")
    mock_logger = mock_current_app.logger
    mock_s3 = Mock()
    mock_s3.Object.side_effect = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "404", "Message": "Not Found"}},
        operation_name="GetObject",
    )
    mock_get_s3_resource.return_value = mock_s3

    bucket_name = "test-bucket"
    file_location = "nonexistent-file.txt"
    access_key = "test-access-key"
    skey = "skey"
    region = "us-west-200"
    result = get_s3_object(bucket_name, file_location, access_key, skey, region)
    assert result is None
    mock_s3.Object.assert_called_once_with(bucket_name, file_location)
    mock_logger.exception.assert_called_once_with(
        f"Can't retrieve S3 Object from {file_location}"
    )
