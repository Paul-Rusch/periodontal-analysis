"""``Evidence`` -- the structured carrier for every metric, classification,
flag, and recommendation produced anywhere in the analytical layer.

Phase 1b spec.  Every classifier (Stage, extent, CDC/AAP, PSR), every
flag-style metric (mucogingival breach, KTW deficiency), every
longitudinal computation (Grade A/B/C, S3 PD-only endpoint), and every
narrative recommendation in Phase 5 returns one of these.  Strings are
never returned in place of an ``Evidence``; bare numbers are never
returned in place of an ``Evidence`` for any *flag-style* output.

The Phase 5 narrative layer is a *pure rendering* of these objects --
no clinical thresholds may appear in narrative source code.

Spec source: handoff plan, Phase 1b.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceStatus(str, Enum):
    """Strict three-state status contract for every ``Evidence`` object.

    * ``SUPPORTED`` -- all required inputs were present and within scope;
      no caveats apply.  Example: ``mean_PD`` for one chart -- every PD
      in the chart is observed, the formula has no missing inputs.

    * ``PROVISIONAL`` -- the rule was computable but with caveats listed
      in ``assumptions`` and/or ``missing_inputs``.  Examples:
        - AAP/EFP Stage III for ``patient_01`` (Stage IV upgrade inputs
          unknown).
        - AAP/EFP Grade C from PERIODONTAL_INTERPRETATION.md sec 15.3
          longitudinal CAL (always provisional because the published
          thresholds are 5-year and the dataset window is shorter --
          the ``"projected from {N}-year window"`` assumption is
          mandatory on every Grade Evidence).

    * ``NOT_ASSESSABLE`` -- one or more required inputs are missing and
      the rule cannot fire either way.  Examples:
        - mucogingival metrics (``KTW``, ``mucogingival_breach``) on
          ``patient_01`` because MGJ was not recorded.
        - Stage IV upgrade alone, before tooth-loss-due-to-perio is
          known.

    The string values match exactly what the handoff plan asked for so
    JSON / markdown rendering is deterministic.
    """

    SUPPORTED = "supported"
    PROVISIONAL = "provisional"
    NOT_ASSESSABLE = "not_assessable"


@dataclass(frozen=True)
class Evidence:
    """One structured fact produced by the analytical layer.

    Field semantics mirror the handoff plan's Phase 1b spec exactly:

    * ``rule_id`` -- stable, hierarchical identifier.  Examples:
      ``"aap_efp_2018.stage.iii"``, ``"cdc_aap.severity.severe"``,
      ``"efp_s3.endpoint.pd_only"``, ``"mgn.mucogingival_breach"``,
      ``"site.pd_class.deep"``.  ``rule_id`` is what downstream
      filtering, audit trails, and the Phase 5 narrative engine key
      off.

    * ``scope`` -- the (patient, exam, arch, surface, tooth, site)
      slice the rule fired on, in order from broadest to narrowest.
      Patient-level rules: ``("patient_01",)``.  Exam-level:
      ``("patient_01", "exam_3")``.  Tooth-level:
      ``("patient_01", "exam_3", "tooth_14")``.  Site-level:
      ``("patient_01", "exam_3", "maxillary", "facial", "tooth_14",
      "distal")``.  Tuple (not list) so ``Evidence`` is hashable.

    * ``status`` -- ``EvidenceStatus``; see the enum docstring.

    * ``value`` -- the typed *result* of a metric (e.g. ``"III"`` for
      a Stage classifier, ``3.4`` for ``mean_PD``, ``True`` for a
      boolean flag, ``None`` for a ``NOT_ASSESSABLE`` rule).  This is
      a small Phase-1b-spec extension noted in the checkpoint message:
      the plan listed ``trigger_measurements`` (the *inputs* that fired
      the rule) but had no field for the *output*; for a metric like
      ``mean_PD`` the value-of-the-metric and the trigger-of-the-rule
      are different things, so they get separate fields.

    * ``threshold_crossed`` -- the rule text in human-readable form,
      e.g. ``"max_interdental_CAL >= 5"``.  Phase 5 may render this
      verbatim; this is the only place clinical thresholds appear as
      strings.

    * ``trigger_measurements`` -- the values that caused the rule to
      fire, as a tuple of dicts.  Each dict's shape is rule-specific
      but should at minimum include ``measurement`` and ``value``.

    * ``missing_inputs`` -- names of inputs whose absence drives the
      ``provisional`` / ``not_assessable`` status.  Adding any of these
      should change or refine the result; this is what the Phase 5
      narrative renders as "this could be tightened up if you also
      gathered ...".

    * ``assumptions`` -- assumptions made to compute the result, e.g.
      ``"projected from 1.66-year window"`` for a longitudinal Grade.
      Mandatory non-empty for ``PROVISIONAL`` Evidence.

    * ``citation`` -- pointer back into PERIODONTAL_INTERPRETATION.md
      and the originating clinical guidance, e.g.
      ``"PERIODONTAL_INTERPRETATION.md sec 6 Stage III; AAP/EFP 2018 [1]"``.

    * ``notes`` -- free-text auditing trail; never used by the
      classification engine, sometimes rendered as a clinician-facing
      footnote.
    """

    rule_id: str
    scope: tuple[Any, ...]
    status: EvidenceStatus
    threshold_crossed: str
    citation: str
    value: Any = None
    trigger_measurements: tuple[dict[str, Any], ...] = ()
    missing_inputs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        # PROVISIONAL Evidence must explain the caveat -- otherwise
        # downstream callers cannot distinguish a real provisional from
        # a forgotten one.
        if (
            self.status is EvidenceStatus.PROVISIONAL
            and not self.assumptions
            and not self.missing_inputs
        ):
            raise ValueError(
                f"Evidence(rule_id={self.rule_id!r}, status=PROVISIONAL) "
                "must list at least one assumption or missing_input"
            )
        # NOT_ASSESSABLE Evidence must declare what's missing.
        if (
            self.status is EvidenceStatus.NOT_ASSESSABLE
            and not self.missing_inputs
        ):
            raise ValueError(
                f"Evidence(rule_id={self.rule_id!r}, status=NOT_ASSESSABLE) "
                "must list at least one missing_input"
            )

    @property
    def is_supported(self) -> bool:
        return self.status is EvidenceStatus.SUPPORTED

    @property
    def is_provisional(self) -> bool:
        return self.status is EvidenceStatus.PROVISIONAL

    @property
    def is_not_assessable(self) -> bool:
        return self.status is EvidenceStatus.NOT_ASSESSABLE

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict.  Tuples become lists; the status
        enum becomes its string value.  Used by the Phase 5 markdown /
        JSON renderers."""
        out: dict[str, Any] = {
            "rule_id": self.rule_id,
            "scope": list(self.scope),
            "status": self.status.value,
            "threshold_crossed": self.threshold_crossed,
            "citation": self.citation,
            "value": _jsonify(self.value),
            "trigger_measurements": [dict(t) for t in self.trigger_measurements],
            "missing_inputs": list(self.missing_inputs),
            "assumptions": list(self.assumptions),
            "notes": self.notes,
        }
        return out

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


def _jsonify(value: Any) -> Any:
    """Recursive best-effort conversion of dataclass / enum values into
    JSON-friendly primitives.  Used by ``Evidence.to_dict`` so a metric
    can put a ``PD(mm=5)`` in ``value`` and still serialize cleanly."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonify(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    return repr(value)
