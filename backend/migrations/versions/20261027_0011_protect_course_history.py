"""protect enrollments and payments when a course is deleted

Revision ID: 20261027_0011
Revises: 20260917_0010
"""
from alembic import op

revision = "20261027_0011"
down_revision = "20260917_0010"
branch_labels = None
depends_on = None

# Created inline in 0004/0005 without names, so PostgreSQL named them <table>_<column>_fkey.
CONSTRAINTS = (("enrollments", "enrollments_course_id_fkey"), ("payment_orders", "payment_orders_course_id_fkey"))


def _recreate(ondelete):
    for table, name in CONSTRAINTS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "courses", ["course_id"], ["id"], ondelete=ondelete)


def upgrade():
    # Deleting a course used to cascade to enrollments and approved payments (accounting records).
    _recreate("RESTRICT")


def downgrade():
    _recreate("CASCADE")
