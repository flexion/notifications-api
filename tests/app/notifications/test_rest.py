import uuid

import pytest
from flask import current_app, json
from freezegun import freeze_time

from app.dao.api_key_dao import save_model_api_key
from app.dao.notifications_dao import dao_update_notification
from app.dao.templates_dao import dao_update_template
from app.enums import KeyType, NotificationStatus, NotificationType, TemplateType
from app.models import ApiKey
from notifications_python_client.authentication import create_jwt_token
from tests import create_service_authorization_header
from tests.app.db import create_api_key, create_notification


@pytest.mark.parametrize("type", (NotificationType.EMAIL, NotificationType.SMS))
def test_get_notification_by_id(
    client, sample_notification, sample_email_notification, type, mocker
):
    mock_s3 = mocker.patch("app.notifications.rest.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mock_s3_personalisation = mocker.patch(
        "app.notifications.rest.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}

    if type == NotificationType.EMAIL:
        notification_to_get = sample_email_notification
    elif type == NotificationType.SMS:
        notification_to_get = sample_notification

    auth_header = create_service_authorization_header(
        service_id=notification_to_get.service_id
    )
    response = client.get(
        "/notifications/{}".format(notification_to_get.id), headers=[auth_header]
    )

    assert response.status_code == 200
    notification = json.loads(response.get_data(as_text=True))["data"]["notification"]
    assert notification["status"] == NotificationStatus.CREATED
    assert notification["template"] == {
        "id": str(notification_to_get.template.id),
        "name": notification_to_get.template.name,
        "template_type": notification_to_get.template.template_type,
        "version": 1,
    }
    assert notification["to"] == notification_to_get.to
    assert notification["service"] == str(notification_to_get.service_id)
    assert notification["body"] == notification_to_get.template.content
    assert notification.get("subject", None) == notification_to_get.subject


@pytest.mark.parametrize("id", ["1234-badly-formatted-id-7890", "0"])
@pytest.mark.parametrize("type", (NotificationType.EMAIL, NotificationType.SMS))
def test_get_notification_by_invalid_id(
    client, sample_notification, sample_email_notification, id, type
):
    if type == NotificationType.EMAIL:
        notification_to_get = sample_email_notification
    elif type == NotificationType.SMS:
        notification_to_get = sample_notification
    auth_header = create_service_authorization_header(
        service_id=notification_to_get.service_id
    )

    response = client.get("/notifications/{}".format(id), headers=[auth_header])

    assert response.status_code == 405


def test_get_notifications_empty_result(client, sample_api_key):
    auth_header = create_service_authorization_header(
        service_id=sample_api_key.service_id
    )

    response = client.get(
        path="/notifications/{}".format(uuid.uuid4()), headers=[auth_header]
    )

    notification = json.loads(response.get_data(as_text=True))
    assert notification["result"] == "error"
    assert notification["message"] == "No result found"
    assert response.status_code == 404


@pytest.mark.parametrize(
    "api_key_type,notification_key_type",
    [
        (KeyType.NORMAL, KeyType.TEAM),
        (KeyType.NORMAL, KeyType.TEST),
        (KeyType.TEST, KeyType.NORMAL),
        (KeyType.TEST, KeyType.TEAM),
        (KeyType.TEAM, KeyType.NORMAL),
        (KeyType.TEAM, KeyType.TEST),
    ],
)
def test_get_notification_from_different_api_key_works(
    client, sample_notification, api_key_type, notification_key_type
):
    sample_notification.key_type = notification_key_type
    api_key = ApiKey(
        service=sample_notification.service,
        name="api_key",
        created_by=sample_notification.service.created_by,
        key_type=api_key_type,
    )
    save_model_api_key(api_key)

    response = client.get(
        path="/notifications/{}".format(sample_notification.id),
        headers=_create_auth_header_from_key(api_key),
    )
    assert response.status_code == 200


@pytest.mark.parametrize("key_type", [KeyType.NORMAL, KeyType.TEAM, KeyType.TEST])
def test_get_notification_from_different_api_key_of_same_type_succeeds(
    client, sample_notification, key_type
):
    creation_api_key = ApiKey(
        service=sample_notification.service,
        name="creation_api_key",
        created_by=sample_notification.service.created_by,
        key_type=key_type,
    )
    save_model_api_key(creation_api_key)

    querying_api_key = ApiKey(
        service=sample_notification.service,
        name="querying_api_key",
        created_by=sample_notification.service.created_by,
        key_type=key_type,
    )
    save_model_api_key(querying_api_key)

    sample_notification.api_key = creation_api_key
    sample_notification.key_type = key_type
    dao_update_notification(sample_notification)

    response = client.get(
        path="/notifications/{}".format(sample_notification.id),
        headers=_create_auth_header_from_key(querying_api_key),
    )

    assert response.status_code == 200
    notification = json.loads(response.get_data(as_text=True))["data"]["notification"]
    assert sample_notification.api_key_id != querying_api_key.id
    assert notification["id"] == str(sample_notification.id)


def test_get_all_notifications(client, sample_notification):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )

    response = client.get("/notifications", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert notifications["notifications"][0]["status"] == NotificationStatus.CREATED
    assert notifications["notifications"][0]["template"] == {
        "id": str(sample_notification.template.id),
        "name": sample_notification.template.name,
        "template_type": sample_notification.template.template_type,
        "version": 1,
    }

    assert notifications["notifications"][0]["to"] == "1"
    assert notifications["notifications"][0]["service"] == str(
        sample_notification.service_id
    )
    assert (
        notifications["notifications"][0]["body"]
        == "Dear Sir/Madam, Hello. Yours Truly, The Government."
    )


def test_normal_api_key_returns_notifications_created_from_jobs_and_from_api(
    client, sample_template, sample_api_key, sample_notification
):
    api_notification = create_notification(
        template=sample_template, api_key=sample_api_key
    )

    response = client.get(
        path="/notifications", headers=_create_auth_header_from_key(sample_api_key)
    )

    assert response.status_code == 200

    notifications = json.loads(response.get_data(as_text=True))["notifications"]
    assert len(notifications) == 2
    assert set(x["id"] for x in notifications) == {
        str(sample_notification.id),
        str(api_notification.id),
    }


@pytest.mark.parametrize("key_type", [KeyType.NORMAL, KeyType.TEAM, KeyType.TEST])
def test_get_all_notifications_only_returns_notifications_of_matching_type(
    client,
    sample_template,
    sample_api_key,
    sample_test_api_key,
    sample_team_api_key,
    key_type,
):
    normal_notification = create_notification(
        sample_template, api_key=sample_api_key, key_type=KeyType.NORMAL
    )
    team_notification = create_notification(
        sample_template, api_key=sample_team_api_key, key_type=KeyType.TEAM
    )
    test_notification = create_notification(
        sample_template, api_key=sample_test_api_key, key_type=KeyType.TEST
    )

    notification_objs = {
        KeyType.NORMAL: normal_notification,
        KeyType.TEAM: team_notification,
        KeyType.TEST: test_notification,
    }

    response = client.get(
        path="/notifications",
        headers=_create_auth_header_from_key(notification_objs[key_type].api_key),
    )

    assert response.status_code == 200

    notifications = json.loads(response.get_data(as_text=True))["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["id"] == str(notification_objs[key_type].id)


@pytest.mark.parametrize("key_type", [KeyType.NORMAL, KeyType.TEAM, KeyType.TEST])
def test_do_not_return_job_notifications_by_default(
    client, sample_template, sample_job, key_type
):
    team_api_key = create_api_key(sample_template.service, KeyType.TEAM)
    normal_api_key = create_api_key(sample_template.service, KeyType.NORMAL)
    test_api_key = create_api_key(sample_template.service, KeyType.TEST)

    create_notification(sample_template, job=sample_job)
    normal_notification = create_notification(sample_template, api_key=normal_api_key)
    team_notification = create_notification(sample_template, api_key=team_api_key)
    test_notification = create_notification(sample_template, api_key=test_api_key)

    notification_objs = {
        KeyType.NORMAL: normal_notification,
        KeyType.TEAM: team_notification,
        KeyType.TEST: test_notification,
    }

    response = client.get(
        path="/notifications",
        headers=_create_auth_header_from_key(notification_objs[key_type].api_key),
    )

    assert response.status_code == 200

    notifications = json.loads(response.get_data(as_text=True))["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["id"] == str(notification_objs[key_type].id)


@pytest.mark.parametrize(
    "key_type", [(KeyType.NORMAL, 2), (KeyType.TEAM, 1), (KeyType.TEST, 1)]
)
def test_only_normal_api_keys_can_return_job_notifications(
    client,
    sample_notification_with_job,
    sample_template,
    sample_api_key,
    sample_team_api_key,
    sample_test_api_key,
    key_type,
    mocker,
):
    mock_s3 = mocker.patch("app.notifications.rest.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mock_s3_personalisation = mocker.patch(
        "app.notifications.rest.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}

    normal_notification = create_notification(
        template=sample_template,
        api_key=sample_api_key,
        key_type=KeyType.NORMAL,
    )
    team_notification = create_notification(
        template=sample_template,
        api_key=sample_team_api_key,
        key_type=KeyType.TEAM,
    )
    test_notification = create_notification(
        template=sample_template,
        api_key=sample_test_api_key,
        key_type=KeyType.TEST,
    )

    notification_objs = {
        KeyType.NORMAL: normal_notification,
        KeyType.TEAM: team_notification,
        KeyType.TEST: test_notification,
    }

    response = client.get(
        path="/notifications?include_jobs=true",
        headers=_create_auth_header_from_key(notification_objs[key_type[0]].api_key),
    )

    assert response.status_code == 200
    notifications = json.loads(response.get_data(as_text=True))["notifications"]
    assert len(notifications) == key_type[1]
    assert notifications[0]["id"] == str(notification_objs[key_type[0]].id)


def test_get_all_notifications_newest_first(client, sample_email_template):
    notification_1 = create_notification(template=sample_email_template)
    notification_2 = create_notification(template=sample_email_template)
    notification_3 = create_notification(template=sample_email_template)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get("/notifications", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert len(notifications["notifications"]) == 3
    assert notifications["notifications"][0]["to"] == notification_3.to
    assert notifications["notifications"][1]["to"] == notification_2.to
    assert notifications["notifications"][2]["to"] == notification_1.to
    assert response.status_code == 200


def test_should_reject_invalid_page_param(client, sample_email_template):
    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get("/notifications?page=invalid", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert notifications["result"] == "error"
    assert "Not a valid integer." in notifications["message"]["page"]


def test_valid_page_size_param(notify_api, sample_email_template):
    with notify_api.test_request_context():
        create_notification(sample_email_template)
        create_notification(sample_email_template)
        with notify_api.test_client() as client:
            auth_header = create_service_authorization_header(
                service_id=sample_email_template.service_id
            )

            response = client.get(
                "/notifications?page=1&page_size=1", headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(notifications["notifications"]) == 1
            assert notifications["total"] == 2
            assert notifications["page_size"] == 1


def test_invalid_page_size_param(client, sample_email_template):
    create_notification(sample_email_template)
    create_notification(sample_email_template)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get(
        "/notifications?page=1&page_size=invalid", headers=[auth_header]
    )

    notifications = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert notifications["result"] == "error"
    assert "Not a valid integer." in notifications["message"]["page_size"]


def test_should_return_pagination_links(client, sample_email_template):
    # Effectively mocking page size
    original_page_size = current_app.config["API_PAGE_SIZE"]
    try:
        current_app.config["API_PAGE_SIZE"] = 1

        create_notification(sample_email_template)
        notification_2 = create_notification(sample_email_template)
        create_notification(sample_email_template)

        auth_header = create_service_authorization_header(
            service_id=sample_email_template.service_id
        )

        response = client.get("/notifications?page=2", headers=[auth_header])

        notifications = json.loads(response.get_data(as_text=True))
        assert len(notifications["notifications"]) == 1
        assert notifications["links"]["last"] == "/notifications?page=3"
        assert notifications["links"]["prev"] == "/notifications?page=1"
        assert notifications["links"]["next"] == "/notifications?page=3"
        assert notifications["notifications"][0]["to"] == notification_2.to
        assert response.status_code == 200

    finally:
        current_app.config["API_PAGE_SIZE"] = original_page_size


def test_get_all_notifications_returns_empty_list(client, sample_api_key):
    auth_header = create_service_authorization_header(
        service_id=sample_api_key.service.id
    )

    response = client.get("/notifications", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert len(notifications["notifications"]) == 0


def test_filter_by_template_type(client, sample_template, sample_email_template):
    create_notification(sample_template)
    create_notification(sample_email_template)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get("/notifications?template_type=sms", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert len(notifications["notifications"]) == 1
    assert (
        notifications["notifications"][0]["template"]["template_type"]
        == TemplateType.SMS
    )
    assert response.status_code == 200


def test_filter_by_multiple_template_types(
    client, sample_template, sample_email_template
):
    create_notification(sample_template)
    create_notification(sample_email_template)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get(
        "/notifications?template_type=sms&template_type=email", headers=[auth_header]
    )

    assert response.status_code == 200
    notifications = json.loads(response.get_data(as_text=True))
    assert len(notifications["notifications"]) == 2
    assert {TemplateType.SMS, TemplateType.EMAIL} == {
        x["template"]["template_type"] for x in notifications["notifications"]
    }


def test_filter_by_status(client, sample_email_template):
    create_notification(sample_email_template, status=NotificationStatus.DELIVERED)
    create_notification(sample_email_template)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get("/notifications?status=delivered", headers=[auth_header])

    notifications = json.loads(response.get_data(as_text=True))
    assert len(notifications["notifications"]) == 1
    assert notifications["notifications"][0]["status"] == NotificationStatus.DELIVERED
    assert response.status_code == 200


def test_filter_by_multiple_statuses(client, sample_email_template):
    create_notification(sample_email_template, status=NotificationStatus.DELIVERED)
    create_notification(sample_email_template, status=NotificationStatus.SENDING)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get(
        "/notifications?status=delivered&status=sending", headers=[auth_header]
    )

    assert response.status_code == 200
    notifications = json.loads(response.get_data(as_text=True))
    assert len(notifications["notifications"]) == 2
    assert {NotificationStatus.DELIVERED, NotificationStatus.SENDING} == {
        x["status"] for x in notifications["notifications"]
    }


def test_filter_by_status_and_template_type(
    client, sample_template, sample_email_template
):
    create_notification(sample_template)
    create_notification(sample_email_template)
    create_notification(sample_email_template, status=NotificationStatus.DELIVERED)

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.get(
        "/notifications?template_type=email&status=delivered", headers=[auth_header]
    )

    notifications = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert len(notifications["notifications"]) == 1
    assert (
        notifications["notifications"][0]["template"]["template_type"]
        == TemplateType.EMAIL
    )
    assert notifications["notifications"][0]["status"] == NotificationStatus.DELIVERED


def test_get_notification_by_id_returns_merged_template_content(
    client, sample_template_with_placeholders
):
    sample_notification = create_notification(
        sample_template_with_placeholders, personalisation={"name": "world"}
    )

    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )

    response = client.get(
        "/notifications/{}".format(sample_notification.id), headers=[auth_header]
    )

    notification = json.loads(response.get_data(as_text=True))["data"]["notification"]
    assert response.status_code == 200
    assert notification["body"] == "Hello world\nYour thing is due soon"
    assert "subject" not in notification
    assert notification["content_char_count"] == 34


def test_get_notification_by_id_returns_merged_template_content_for_email(
    client, sample_email_template_with_placeholders, mocker
):
    # mock_s3 = mocker.patch("app.notifications.rest.get_personalisation_from_s3")
    # mock_s3.return_value = {"name": "foo"}
    sample_notification = create_notification(
        sample_email_template_with_placeholders, personalisation={"name": "world"}
    )
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )

    response = client.get(
        "/notifications/{}".format(sample_notification.id), headers=[auth_header]
    )

    notification = json.loads(response.get_data(as_text=True))["data"]["notification"]
    assert response.status_code == 200
    assert notification["body"] == "Hello world\nThis is an email from GOV.UK"
    assert notification["subject"] == "world"
    assert notification["content_char_count"] is None


def test_get_notifications_for_service_returns_merged_template_content(
    client, sample_template_with_placeholders, mocker
):
    mock_s3 = mocker.patch("app.notifications.rest.get_personalisation_from_s3")
    mock_s3.return_value = {"name": "foo"}
    with freeze_time("2001-01-01T12:00:00"):
        create_notification(
            sample_template_with_placeholders,
            personalisation={"name": "merged with first"},
        )

    with freeze_time("2001-01-01T12:00:01"):
        create_notification(
            sample_template_with_placeholders,
            personalisation={"name": "merged with second"},
        )

    auth_header = create_service_authorization_header(
        service_id=sample_template_with_placeholders.service_id
    )

    response = client.get(path="/notifications", headers=[auth_header])
    assert response.status_code == 200

    assert {
        noti["body"]
        for noti in json.loads(response.get_data(as_text=True))["notifications"]
    } == {
        "Hello merged with first\nYour thing is due soon",
        "Hello merged with second\nYour thing is due soon",
    }


def test_get_notification_selects_correct_template_for_personalisation(
    client, notify_db_session, sample_template, mocker
):
    create_notification(sample_template)
    original_content = sample_template.content
    sample_template.content = "((name))"
    dao_update_template(sample_template)
    notify_db_session.commit()

    mock_s3 = mocker.patch("app.notifications.rest.get_personalisation_from_s3")
    mock_s3.return_value = {"name": "foo"}

    create_notification(sample_template, personalisation={"name": "foo"})

    auth_header = create_service_authorization_header(
        service_id=sample_template.service_id
    )

    response = client.get(path="/notifications", headers=[auth_header])

    assert response.status_code == 200

    resp = json.loads(response.get_data(as_text=True))
    notis = sorted(resp["notifications"], key=lambda x: x["template_version"])
    assert len(notis) == 2
    assert notis[0]["template_version"] == 1
    assert notis[0]["body"] == original_content
    assert notis[1]["template_version"] == 2
    assert notis[1]["body"] == "foo"

    assert notis[0]["template_version"] == notis[0]["template"]["version"]
    assert notis[1]["template_version"] == notis[1]["template"]["version"]


def _create_auth_header_from_key(api_key):
    token = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))
    return [("Authorization", "Bearer {}".format(token))]
