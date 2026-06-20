from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5dd11ee35efb'
down_revision: Union[str, Sequence[str], None] = 'c7ccc2d12941'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_bookings_status'), table_name='bookings')
    op.create_index(
        'ix_bookings_created_at_id_status',
        'bookings',
        ['created_at', 'id', 'status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_bookings_created_at_id_status', table_name='bookings')
    op.create_index(op.f('ix_bookings_status'), 'bookings', ['status'], unique=False)
