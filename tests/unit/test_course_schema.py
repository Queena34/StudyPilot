from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.course import CourseCreate, CourseUpdate


def test_course_create_strips_text() -> None:
    course = CourseCreate(name="  Machine Learning  ", exam_date=date(2027, 1, 20))
    assert course.name == "Machine Learning"


def test_course_create_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        CourseCreate(name="   ")


def test_course_update_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        CourseUpdate(name="   ")
