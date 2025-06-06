from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import case

from app import db
from app.dao.dao_utils import autocommit
from app.models import FactProcessingTime
from app.utils import utc_now


@autocommit
def insert_update_processing_time(processing_time):
    """
    This uses the Postgres upsert to avoid race conditions when two threads try and insert
    at the same row. The excluded object refers to values that we tried to insert but were
    rejected.
    http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    """
    table = FactProcessingTime.__table__
    stmt = insert(table).values(
        local_date=processing_time.local_date,
        messages_total=processing_time.messages_total,
        messages_within_10_secs=processing_time.messages_within_10_secs,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.local_date],
        set_={
            "messages_total": stmt.excluded.messages_total,
            "messages_within_10_secs": stmt.excluded.messages_within_10_secs,
            "updated_at": utc_now(),
        },
    )
    db.session.connection().execute(stmt)


def get_processing_time_percentage_for_date_range(start_date, end_date):
    query = (
        select(
            FactProcessingTime.local_date.cast(db.Text).label("date"),
            FactProcessingTime.messages_total,
            FactProcessingTime.messages_within_10_secs,
            case(
                (
                    FactProcessingTime.messages_total > 0,
                    (
                        (
                            FactProcessingTime.messages_within_10_secs
                            / FactProcessingTime.messages_total.cast(db.Float)
                        )
                        * 100
                    ),
                ),
                (FactProcessingTime.messages_total == 0, 100.0),
            ).label("percentage"),
        )
        .where(
            FactProcessingTime.local_date >= start_date,
            FactProcessingTime.local_date <= end_date,
        )
        .order_by(FactProcessingTime.local_date)
    )

    return db.session.execute(query).all()
