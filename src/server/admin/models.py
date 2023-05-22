from sqlalchemy import Table, ForeignKey, Column, Integer, String, Date, delete, update
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from copy import deepcopy

from .._db import session
from delphi.epidata.common.logger import get_structured_logger

from typing import Set, Optional, List
from datetime import datetime as dtime


Base = declarative_base()

association_table = Table(
    "user_role_link",
    Base.metadata,
    Column("user_id", ForeignKey("api_user.id")),
    Column("role_id", ForeignKey("user_role.id")),
)


class User(Base):
    __tablename__ = "api_user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    roles = relationship("UserRole", secondary=association_table)
    api_key = Column(String(50), unique=True, nullable=False)
    email = Column(String(320), unique=True, nullable=False)
    created = Column(Date, default=dtime.strftime(dtime.now(), "%Y-%m-%d"))
    last_time_used = Column(Date, default=dtime.strftime(dtime.now(), "%Y-%m-%d"))

    def __init__(self, api_key: str, email: str = None) -> None:
        self.api_key = api_key
        self.email = email

    @staticmethod
    def list_users() -> List["User"]:
        return session.query(User).all()

    @property
    def as_dict(self):
        user_dict = deepcopy(self.__dict__)  # NOTE: changed from `self.__dict__.copy()` as it caused issues
        # so we dont change the internal representation of self
        user_dict["roles"] = self.get_user_roles
        try:
            return {k: user_dict[k] for k in ["id", "api_key", "email", "roles", "created", "last_time_used"]}
        except KeyError:
            return {
                "id": self.id,
                "api_key": self.api_key,
                "email": self.email,
                "roles": self.get_user_roles,
                "created": self.created,
                "last_time_used": self.last_time_used
            }

    @property
    def get_user_roles(self) -> Set[str]:
        return set([role.name for role in self.roles])

    def has_role(self, required_role: str) -> bool:
        return required_role in self.get_user_roles

    @staticmethod
    def assign_roles(user: "User", roles: Optional[Set[str]]) -> None:
        get_structured_logger("api_user_models").info("setting roles", roles=roles, user_id=user.id, api_key=user.api_key)
        if roles:
            roles_to_assign = session.query(UserRole).filter(UserRole.name.in_(roles)).all()
            user.roles = roles_to_assign
            session.commit()
        else:
            user.roles = []
            session.commit()

    @staticmethod
    def find_user(*, # asterisk forces explicit naming of all arguments when calling this method
        user_id: Optional[int] = None, api_key: Optional[str] = None, user_email: Optional[str] = None
    ) -> "User":
        user = (
            session.query(User)
            .filter((User.id == user_id) | (User.api_key == api_key) | (User.email == user_email))
            .first()
        )
        return user if user else None

    @staticmethod
    def create_user(api_key: str, email: str, user_roles: Optional[Set[str]] = None) -> "User":
        get_structured_logger("api_user_models").info("creating user", api_key=api_key)
        new_user = User(api_key=api_key, email=email)
        session.add(new_user)
        session.commit()
        User.assign_roles(new_user, user_roles)
        return new_user

    @staticmethod
    def update_user(
        user: "User",
        email: Optional[str],
        api_key: Optional[str],
        roles: Optional[Set[str]]
    ) -> "User":
        get_structured_logger("api_user_models").info("updating user", user_id=user.id, new_api_key=api_key)
        user = User.find_user(user_id=user.id)
        if user:
            update_stmt = (
                update(User)
                .where(User.id == user.id)
                .values(api_key=api_key, email=email)
            )
            session.execute(update_stmt)
            session.commit()
            User.assign_roles(user, roles)
        return user

    @staticmethod
    def delete_user(user_id: int) -> None:
        get_structured_logger("api_user_models").info("deleting user", user_id=user_id)
        session.execute(delete(User).where(User.id == user_id))
        session.commit()


class UserRole(Base):
    __tablename__ = "user_role"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True)

    @staticmethod
    def create_role(name: str) -> None:
        get_structured_logger("api_user_models").info("creating user role", role=name)
        session.execute(
            f"""
        INSERT INTO user_role (name)
        SELECT '{name}'
        WHERE NOT EXISTS
            (SELECT *
            FROM user_role
            WHERE name='{name}')
        """
        )
        session.commit()

    @staticmethod
    def list_all_roles():
        roles = session.query(UserRole).all()
        return [role.name for role in roles]