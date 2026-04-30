"""PipelineAssembler wiring tests (post-M5).

Triage + ResumeResolver + TurnSummarizer were retired when the planner
became the single decision engine and `MemoryWriter` took over rolling
summary duties. The assembler now exposes only:

    adapters   : memory / memory_builder / memory_writer / planner /
                 agent_executor / synthesizer
    stages     : build_planning_stage / build_finalization_stage
"""
from __future__ import annotations

from types import SimpleNamespace

from app.runtime.assembler import PipelineAssembler


def _assembler() -> PipelineAssembler:
    return PipelineAssembler(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )


def test_pipeline_assembler_cached_properties_are_singletons_per_pipeline():
    assembler = _assembler()

    assert assembler.memory_builder is assembler.memory_builder
    assert assembler.memory_writer is assembler.memory_writer
    assert assembler.planner is assembler.planner
    assert assembler.agent_executor is assembler.agent_executor
    assert assembler.synthesizer is assembler.synthesizer


def test_pipeline_assembler_stage_factories_return_fresh_instances():
    assembler = _assembler()

    planning_stage_1 = assembler.build_planning_stage(
        max_iterations=3,
    )
    planning_stage_2 = assembler.build_planning_stage(
        max_iterations=3,
    )
    assert planning_stage_1 is not planning_stage_2
    assert planning_stage_1._planner is assembler.planner
    assert planning_stage_1._agent is assembler.agent_executor
    assert planning_stage_1._max_iterations == 3

    final_stage_1 = assembler.build_finalization_stage()
    final_stage_2 = assembler.build_finalization_stage()
    assert final_stage_1 is not final_stage_2
    assert final_stage_1._synth is assembler.synthesizer


def test_pipeline_assembler_does_not_expose_removed_adapters():
    """Defensive: triage / summary / resume / memory persistence should
    truly be gone so accidental references fail loudly after rebase."""
    assembler = _assembler()
    assert not hasattr(assembler, "triage")
    assert not hasattr(assembler, "summary")
    assert not hasattr(assembler, "resume")
    assert not hasattr(assembler, "memory")  # M6: legacy WM persistence gone
    assert not hasattr(assembler, "build_triage_stage")
