from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CVaRConfig(BaseModel):  # type: ignore
    number_of_realizations: Optional[int] = Field(
        default=None,
        description="""The number of realizations used for CVaR estimation.

Sets the number of realizations that is used to calculate the total objective.

This option is exclusive with the **percentile** option.
""",
    )
    percentile: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="""The percentile used for CVaR estimation.

Sets the percentile of distribution of the objective over the realizations that
is used to calculate the total objective.

This option is exclusive with the **number_of_realizations** option.

        """,
    )

    @model_validator(mode="before")
    @classmethod
    def validate_mutex_nreals_percentile(cls, values):  # pylint: disable=E0213
        has_nreals = values.get("number_of_realizations") is not None
        has_percentile = values.get("percentile") is not None

        if not (has_nreals ^ has_percentile):
            raise ValueError(
                "Invalid CVaR section; Specify only one of the"
                " following: number_of_realizations, percentile"
            )

        return values

    model_config = ConfigDict(
        extra="forbid",
        metadata={
            "doc": """Directs the optimizer to use CVaR estimation.

When this section is present Everest will use Conditional Value at Risk (CVaR)
to minimize risk. Effectively this means that at each iteration the objective
and constraint functions will be calculated as the mean over the sub-set of the
realizations that perform worst. The size of this set is specified as an
absolute number or as a percentile value. These options are selected by setting
either the **number_of_realizations** option, or the **percentile** option,
which are mutually exclusive.
"""
        },
    )
