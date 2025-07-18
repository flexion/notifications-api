import uuid
from datetime import datetime, timedelta
from functools import partial

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.dao.jobs_dao import (
    dao_create_job,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id,
    dao_get_jobs_older_than_data_retention,
    dao_get_notification_outcomes_for_job,
    dao_set_scheduled_jobs_to_pending,
    dao_update_job,
    find_jobs_with_missing_rows,
    find_missing_row_for_job,
)
from app.enums import JobStatus, NotificationStatus
from app.models import Job, NotificationType, TemplateType
from app.utils import utc_now
from tests.app.db import (
    create_job,
    create_notification,
    create_service,
    create_template,
)


def test_should_count_of_statuses_for_notifications_associated_with_job(
    sample_template, sample_job
):
    create_notification(
        sample_template, job=sample_job, status=NotificationStatus.CREATED
    )
    create_notification(
        sample_template, job=sample_job, status=NotificationStatus.CREATED
    )
    create_notification(
        sample_template, job=sample_job, status=NotificationStatus.CREATED
    )
    create_notification(
        sample_template, job=sample_job, status=NotificationStatus.SENDING
    )
    create_notification(
        sample_template, job=sample_job, status=NotificationStatus.DELIVERED
    )

    results = dao_get_notification_outcomes_for_job(
        sample_template.service_id, sample_job.id
    )
    assert {row.status: row.count for row in results} == {
        NotificationStatus.CREATED: 3,
        NotificationStatus.SENDING: 1,
        NotificationStatus.DELIVERED: 1,
    }


def test_should_return_zero_length_array_if_no_notifications_for_job(
    sample_service, sample_job
):
    assert (
        len(dao_get_notification_outcomes_for_job(sample_job.id, sample_service.id))
        == 0
    )


def test_should_return_notifications_only_for_this_job(sample_template):
    job_1 = create_job(sample_template)
    job_2 = create_job(sample_template)

    create_notification(sample_template, job=job_1, status=NotificationStatus.CREATED)
    create_notification(sample_template, job=job_2, status=NotificationStatus.SENT)

    results = dao_get_notification_outcomes_for_job(
        sample_template.service_id, job_1.id
    )
    assert {row.status: row.count for row in results} == {NotificationStatus.CREATED: 1}


def test_should_return_notifications_only_for_this_service(
    sample_notification_with_job,
):
    other_service = create_service(service_name="one")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template)

    create_notification(other_template, job=other_job)

    assert (
        len(
            dao_get_notification_outcomes_for_job(
                sample_notification_with_job.service_id, other_job.id
            )
        )
        == 0
    )
    assert (
        len(
            dao_get_notification_outcomes_for_job(
                other_service.id, sample_notification_with_job.id
            )
        )
        == 0
    )


def test_create_sample_job(sample_template):
    stmt = select(func.count()).select_from(Job)
    assert db.session.execute(stmt).scalar() == 0

    job_id = uuid.uuid4()
    data = {
        "id": job_id,
        "service_id": sample_template.service.id,
        "template_id": sample_template.id,
        "template_version": sample_template.version,
        "original_file_name": "some.csv",
        "notification_count": 1,
        "created_by": sample_template.created_by,
    }

    job = Job(**data)
    dao_create_job(job)
    stmt = select(func.count()).select_from(Job)
    assert db.session.execute(stmt).scalar() == 1
    job_from_db = db.session.get(Job, job_id)
    assert job == job_from_db
    assert job_from_db.notifications_delivered == 0
    assert job_from_db.notifications_failed == 0


def test_get_job_by_id(sample_job):
    job_from_db = dao_get_job_by_service_id_and_job_id(
        sample_job.service.id, sample_job.id
    )
    assert sample_job == job_from_db


def test_get_jobs_for_service(sample_template):
    one_job = create_job(sample_template)

    other_service = create_service(service_name="other service")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template)

    one_job_from_db = dao_get_jobs_by_service_id(one_job.service_id).items
    other_job_from_db = dao_get_jobs_by_service_id(other_job.service_id).items

    assert len(one_job_from_db) == 1
    assert one_job == one_job_from_db[0]

    assert len(other_job_from_db) == 1
    assert other_job == other_job_from_db[0]

    assert one_job_from_db != other_job_from_db


def test_get_jobs_for_service_with_limit_days_param(sample_template):
    one_job = create_job(sample_template)
    old_job = create_job(sample_template, created_at=datetime.now() - timedelta(days=8))

    jobs = dao_get_jobs_by_service_id(one_job.service_id).items

    assert len(jobs) == 2
    assert one_job in jobs
    assert old_job in jobs

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 1
    assert one_job in jobs_limit_days
    assert old_job not in jobs_limit_days


@freeze_time("2017-06-10")
def test_get_jobs_for_service_with_limit_days_edge_case(sample_template):
    one_job = create_job(sample_template)
    just_after_midnight_job = create_job(
        sample_template, created_at=datetime(2017, 6, 3, 0, 0, 1)
    )
    just_before_midnight_job = create_job(
        sample_template, created_at=datetime(2017, 6, 2, 23, 59, 0)
    )

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 2
    assert one_job in jobs_limit_days
    assert just_after_midnight_job in jobs_limit_days
    assert just_before_midnight_job not in jobs_limit_days


def test_get_jobs_for_service_in_processed_at_then_created_at_order(
    notify_db_session, sample_template
):
    from_hour = partial(datetime, 2001, 1, 1)

    created_jobs = [
        create_job(sample_template, created_at=from_hour(2), processing_started=None),
        create_job(sample_template, created_at=from_hour(1), processing_started=None),
        create_job(
            sample_template, created_at=from_hour(1), processing_started=from_hour(4)
        ),
        create_job(
            sample_template, created_at=from_hour(2), processing_started=from_hour(3)
        ),
    ]

    expected_order = sorted(
        created_jobs,
        key=lambda job: ((job.processing_started or job.created_at), str(job.id)),
        reverse=True,
    )

    jobs = dao_get_jobs_by_service_id(sample_template.service.id).items

    assert len(jobs) == len(expected_order)

    for index in range(len(expected_order)):
        assert jobs[index].id == expected_order[index].id


def test_update_job(sample_job):
    assert sample_job.job_status == JobStatus.PENDING

    sample_job.job_status = JobStatus.IN_PROGRESS

    dao_update_job(sample_job)

    job_from_db = db.session.get(Job, sample_job.id)

    assert job_from_db.job_status == JobStatus.IN_PROGRESS


def test_set_scheduled_jobs_to_pending_gets_all_jobs_in_scheduled_state_before_now(
    sample_template,
):
    one_minute_ago = utc_now() - timedelta(minutes=1)
    one_hour_ago = utc_now() - timedelta(minutes=60)
    job_new = create_job(
        sample_template,
        scheduled_for=one_minute_ago,
        job_status=JobStatus.SCHEDULED,
    )
    job_old = create_job(
        sample_template,
        scheduled_for=one_hour_ago,
        job_status=JobStatus.SCHEDULED,
    )
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].id == job_old.id
    assert jobs[1].id == job_new.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_not_scheduled(
    sample_template, sample_job
):
    one_minute_ago = utc_now() - timedelta(minutes=1)
    job_scheduled = create_job(
        sample_template,
        scheduled_for=one_minute_ago,
        job_status=JobStatus.SCHEDULED,
    )
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 1
    assert jobs[0].id == job_scheduled.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_scheduled_in_the_future(
    sample_scheduled_job,
):
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 0


def test_set_scheduled_jobs_to_pending_updates_rows(sample_template):
    one_minute_ago = utc_now() - timedelta(minutes=1)
    one_hour_ago = utc_now() - timedelta(minutes=60)
    create_job(
        sample_template,
        scheduled_for=one_minute_ago,
        job_status=JobStatus.SCHEDULED,
    )
    create_job(
        sample_template,
        scheduled_for=one_hour_ago,
        job_status=JobStatus.SCHEDULED,
    )
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].job_status == JobStatus.PENDING
    assert jobs[1].job_status == JobStatus.PENDING


def test_get_future_scheduled_job_gets_a_job_yet_to_send(sample_scheduled_job):
    result = dao_get_future_scheduled_job_by_id_and_service_id(
        sample_scheduled_job.id, sample_scheduled_job.service_id
    )
    assert result.id == sample_scheduled_job.id


@freeze_time("2016-10-31 10:00:00")
def test_should_get_jobs_seven_days_old(sample_template):
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    seven_days_ago = utc_now() - timedelta(days=7)
    within_seven_days = seven_days_ago + timedelta(seconds=1)

    eight_days_ago = seven_days_ago - timedelta(days=1)

    nine_days_ago = eight_days_ago - timedelta(days=2)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    create_job(sample_template, created_at=seven_days_ago)
    create_job(sample_template, created_at=within_seven_days)
    job_to_delete = create_job(sample_template, created_at=eight_days_ago)
    create_job(sample_template, created_at=nine_days_ago, archived=True)
    create_job(sample_template, created_at=nine_days_one_second_ago, archived=True)

    jobs = dao_get_jobs_older_than_data_retention(
        notification_types=[sample_template.template_type]
    )

    assert len(jobs) == 1
    assert jobs[0].id == job_to_delete.id


def test_get_jobs_for_service_is_paginated(
    notify_db_session, sample_service, sample_template
):
    with freeze_time("2015-01-01T00:00:00") as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(sample_template)

    res = dao_get_jobs_by_service_id(sample_service.id, page=1, page_size=2)

    assert res.per_page == 2
    assert res.total == 10
    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2015, 1, 1, 10)
    assert res.items[1].created_at == datetime(2015, 1, 1, 9)

    res = dao_get_jobs_by_service_id(sample_service.id, page=2, page_size=2)

    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2015, 1, 1, 8)
    assert res.items[1].created_at == datetime(2015, 1, 1, 7)


@pytest.mark.parametrize(
    "file_name",
    [
        "Test message",
        "Report",
    ],
)
def test_get_jobs_for_service_doesnt_return_test_messages(
    sample_template,
    sample_job,
    file_name,
):
    create_job(
        sample_template,
        original_file_name=file_name,
    )

    jobs = dao_get_jobs_by_service_id(sample_job.service_id).items

    assert jobs == [sample_job]


@freeze_time("2016-10-31 10:00:00")
def test_should_get_jobs_seven_days_old_by_scheduled_for_date(sample_service):
    six_days_ago = utc_now() - timedelta(days=6)
    eight_days_ago = utc_now() - timedelta(days=8)
    sms_template = create_template(sample_service, template_type=TemplateType.SMS)

    create_job(sms_template, created_at=eight_days_ago)
    create_job(sms_template, created_at=eight_days_ago, scheduled_for=eight_days_ago)
    job_to_remain = create_job(
        sms_template, created_at=eight_days_ago, scheduled_for=six_days_ago
    )

    jobs = dao_get_jobs_older_than_data_retention(
        notification_types=[NotificationType.SMS]
    )

    assert len(jobs) == 2
    assert job_to_remain.id not in [job.id for job in jobs]


def assert_job_stat(job, result, sent, delivered, failed):
    assert result.job_id == job.id
    assert result.original_file_name == job.original_file_name
    assert result.created_at == job.created_at
    assert result.scheduled_for == job.scheduled_for
    assert result.template_id == job.template_id
    assert result.template_version == job.template_version
    assert result.job_status == job.job_status
    assert result.service_id == job.service_id
    assert result.notification_count == job.notification_count
    assert result.sent == sent
    assert result.delivered == delivered
    assert result.failed == failed


def test_find_jobs_with_missing_rows(sample_email_template):
    healthy_job = create_job(
        template=sample_email_template,
        notification_count=3,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=20),
    )
    for i in range(0, 3):
        create_notification(job=healthy_job, job_row_number=i)
    job_with_missing_rows = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job_with_missing_rows, job_row_number=i)

    results = find_jobs_with_missing_rows()

    assert len(results) == 1
    assert results[0] == job_with_missing_rows


def test_find_jobs_with_missing_rows_returns_nothing_for_a_job_completed_less_than_10_minutes_ago(
    sample_email_template,
):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=9),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    results = find_jobs_with_missing_rows()

    assert len(results) == 0


def test_find_jobs_with_missing_rows_returns_nothing_for_a_job_completed_more_that_a_day_ago(
    sample_email_template,
):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(days=1),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    results = find_jobs_with_missing_rows()

    assert len(results) == 0


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.PENDING,
        JobStatus.IN_PROGRESS,
        JobStatus.CANCELLED,
        JobStatus.SCHEDULED,
    ],
)
def test_find_jobs_with_missing_rows_doesnt_return_jobs_that_are_not_finished(
    sample_email_template, status
):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=status,
        processing_finished=utc_now() - timedelta(minutes=11),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    results = find_jobs_with_missing_rows()

    assert len(results) == 0


def test_find_missing_row_for_job(sample_email_template):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=11),
    )
    create_notification(job=job, job_row_number=0)
    create_notification(job=job, job_row_number=1)
    create_notification(job=job, job_row_number=3)
    create_notification(job=job, job_row_number=4)

    results = find_missing_row_for_job(job.id, 5)
    assert len(results) == 1
    assert results[0].missing_row == 2


def test_find_missing_row_for_job_more_than_one_missing_row(sample_email_template):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=11),
    )
    create_notification(job=job, job_row_number=0)
    create_notification(job=job, job_row_number=1)
    create_notification(job=job, job_row_number=4)

    results = find_missing_row_for_job(job.id, 5)
    assert len(results) == 2
    assert results[0].missing_row == 2
    assert results[1].missing_row == 3


def test_find_missing_row_for_job_return_none_when_row_isnt_missing(
    sample_email_template,
):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=11),
    )
    for i in range(0, 5):
        create_notification(job=job, job_row_number=i)

    results = find_missing_row_for_job(job.id, 5)
    assert len(results) == 0


def test_unique_key_on_job_id_and_job_row_number(sample_email_template):
    job = create_job(template=sample_email_template)
    create_notification(job=job, job_row_number=0)
    with pytest.raises(expected_exception=IntegrityError):
        create_notification(job=job, job_row_number=0)


def test_unique_key_on_job_id_and_job_row_number_no_error_if_row_number_for_different_job(
    sample_email_template,
):
    job_1 = create_job(template=sample_email_template)
    job_2 = create_job(template=sample_email_template)
    create_notification(job=job_1, job_row_number=0)
    create_notification(job=job_2, job_row_number=0)


def test_jobs_with_same_activity_time_are_sorted_by_id(sample_template):
    from datetime import datetime

    dt = datetime(2023, 1, 1, 12, 0, 0)

    job1 = create_job(sample_template, created_at=dt, processing_started=None)
    job2 = create_job(sample_template, created_at=dt, processing_started=None)

    if str(job1.id) < str(job2.id):
        job1, job2 = job2, job1

    jobs = dao_get_jobs_by_service_id(sample_template.service.id).items

    assert jobs[0].id == job1.id
    assert jobs[1].id == job2.id
