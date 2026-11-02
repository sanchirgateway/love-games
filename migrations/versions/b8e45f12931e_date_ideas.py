"""date ideas, votes and built-in ideas

Revision ID: b8e45f12931e
Revises: f3c1a8d5e702
Create Date: 2026-10-26 23:40:10.059190

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e45f12931e'
down_revision: Union[str, Sequence[str], None] = 'f3c1a8d5e702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Встроенные идеи (created_by = NULL): колода не пустая с первого дня. Список зафиксирован в миграции,
# новые встроенные идеи — следующей миграцией
BUILTIN_IDEAS = [
    ("Пикник в парке", "Плед, термос и бутерброды — и никуда не спешить"),
    ("Планетарий", "Посмотреть на звёзды, даже если в городе их не видно"),
    ("Готовим новое блюдо", "Выбрать рецепт кухни, которую ещё не пробовали, и приготовить вместе"),
    ("Квест-комната", "Час, чтобы выбраться вместе — проверка командной работы"),
    ("Кино под открытым небом", "Или домашний кинотеатр с проектором и пледами"),
    ("Мастер-класс по гончарному делу", "Слепить друг другу по кружке"),
    ("Рассвет", "Встать затемно и встретить рассвет в красивом месте"),
    ("Прогулка без маршрута", "Сворачивать туда, куда захочется, и зайти в первое понравившееся кафе"),
    ("Настольные игры", "Вечер настолок дома или в антикафе"),
    ("Каток", "Горячий чай после — обязательно"),
    ("Музей или выставка", "Выбрать ту, где никто из вас ещё не был"),
    ("Завтрак в новом месте", "Медленный выходной завтрак в кафе, куда давно хотели"),
    ("Караоке", "Спеть дуэтом хотя бы одну песню"),
    ("Велопрогулка", "Арендовать велосипеды или самокаты и уехать подальше"),
    ("Дегустация", "Вина, сыра, чая или кофе — что больше нравится"),
    ("Фотопрогулка", "Снимать друг друга и город, потом выбрать лучшие кадры"),
    ("Танцевальный урок", "Сальса, бачата или вальс — пробное занятие для двоих"),
    ("Поездка на один день", "Электричка или машина до ближайшего города, где не были"),
    ("Спа-вечер дома", "Маски, ванна с пеной, массаж и спокойная музыка"),
    ("Стендап или импровизация", "Посмеяться вместе на живом выступлении"),
    ("Концерт", "Любимый исполнитель или новый для обоих"),
    ("Ужин при свечах дома", "Накрыть стол как в ресторане и одеться красиво"),
    ("Блошиный рынок", "Найти друг другу самую странную вещь до 500 ₽"),
    ("Скалодром", "Пробное занятие — страховать друг друга"),
    ("Ботанический сад или оранжерея", "Тропики посреди города"),
    ("Вечер воспоминаний", "Пересмотреть старые фото и рассказать, что помнит каждый"),
    ("Боулинг или бильярд", "Проигравший угощает десертом"),
    ("Кулинарный мастер-класс", "Паста, суши или пельмени под руководством шефа"),
    ("Обзорная площадка на закате", "Найти самую высокую точку города"),
    ("Нарисовать портреты друг друга", "Без умения рисовать — так даже веселее"),
]


def upgrade() -> None:
    """Upgrade schema."""
    date_ideas = op.create_table('date_ideas',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('place', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_date_ideas_created_by'), 'date_ideas', ['created_by'], unique=False)
    op.create_table('date_idea_votes',
    sa.Column('idea_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('vote', sa.Enum('yes', 'no', name='idea_vote'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['idea_id'], ['date_ideas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('idea_id', 'user_id')
    )
    op.create_index(op.f('ix_date_idea_votes_user_id'), 'date_idea_votes', ['user_id'], unique=False)
    op.add_column('dates', sa.Column('idea_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_dates_idea_id'), 'dates', ['idea_id'], unique=False)
    op.create_foreign_key(
        'fk_dates_idea_id_date_ideas', 'dates', 'date_ideas', ['idea_id'], ['id'], ondelete='SET NULL'
    )

    op.bulk_insert(
        date_ideas,
        [{'id': uuid4(), 'title': title, 'description': description} for title, description in BUILTIN_IDEAS],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_dates_idea_id_date_ideas', 'dates', type_='foreignkey')
    op.drop_index(op.f('ix_dates_idea_id'), table_name='dates')
    op.drop_column('dates', 'idea_id')
    op.drop_index(op.f('ix_date_idea_votes_user_id'), table_name='date_idea_votes')
    op.drop_table('date_idea_votes')
    op.drop_index(op.f('ix_date_ideas_created_by'), table_name='date_ideas')
    op.drop_table('date_ideas')
    # Enum-типы Postgres создаются вместе с таблицами, но сами не удаляются
    sa.Enum(name='idea_vote').drop(op.get_bind(), checkfirst=True)
