"""Separate, disabled-by-default contracts. No school URLs, password collection or scraping.

An approved provider must validate identity assertions server-side. Timetable access
requires its own explicit consent and scope; an SSO assertion never grants it.
No provider is configured or invoked against a school in phase one.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class UniversityIdentity:
    subject: str
    university: str = ''
    name: str = ''
    major: str = ''
    academic_year: str = ''
    faculty: str = ''


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    term: str


@dataclass(frozen=True)
class ClassMeeting:
    # Approved adapter expands weekly patterns into dated, timezone-aware intervals.
    starts: datetime
    ends: datetime
    course_code: str = ''
    required: bool = True


@dataclass(frozen=True)
class AcademicContext:
    courses: tuple[Course, ...] = ()
    meetings: tuple[ClassMeeting, ...] = ()
    courses_authorized: bool = False
    timetable_authorized: bool = False


class IdentityProvider(Protocol):
    def authenticate(self, validated_response: object) -> UniversityIdentity: ...


class CourseDataProvider(Protocol):
    def read_authorized(self, user_id: int) -> AcademicContext: ...


def academic_context(user_id):
    # Intentionally no integration configured. Unknown availability stays unknown.
    return AcademicContext()
