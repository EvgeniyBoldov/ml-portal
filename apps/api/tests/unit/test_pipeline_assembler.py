from __future__ import annotations

from types import SimpleNamespace

from app.runtime.assembler import PipelineAssembler


def test_pipeline_assembler_cached_properties_are_singletons_per_pipeline():
    assembler = PipelineAssembler(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )

    assert assembler.memory is assembler.memory
    assert assembler.triage is assembler.triage
    assert assembler.planner is assembler.planner
    assert assembler.agent_executor is assembler.agent_executor
    assert assembler.synthesizer is assembler.synthesizer
    assert assembler.summary is assembler.summary
    assert assembler.resume is assembler.resume
    assert assembler.resume._memory is assembler.memory


def test_pipeline_assembler_stage_factories_return_fresh_instances():
    assembler = PipelineAssembler(
        session=SimpleNamespace(),
        llm_client=SimpleNamespace(),
        run_store=None,
    )

    triage_stage_1 = assembler.build_triage_stage()
    triage_stage_2 = assembler.build_triage_stage()
    assert triage_stage_1 is not triage_stage_2
    assert triage_stage_1._triage is assembler.triage
    assert triage_stage_1._memory is assembler.memory

    planning_stage_1 = assembler.build_planning_stage(
        max_iterations=3,
        max_wall_time_ms=1000,
    )
    planning_stage_2 = assembler.build_planning_stage(
        max_iterations=3,
        max_wall_time_ms=1000,
    )
    assert planning_stage_1 is not planning_stage_2
    assert planning_stage_1._planner is assembler.planner
    assert planning_stage_1._agent is assembler.agent_executor
    assert planning_stage_1._memory is assembler.memory
    assert planning_stage_1._max_iterations == 3
    assert planning_stage_1._max_wall_time_ms == 1000

    final_stage_1 = assembler.build_finalization_stage()
    final_stage_2 = assembler.build_finalization_stage()
    assert final_stage_1 is not final_stage_2
    assert final_stage_1._synth is assembler.synthesizer
    assert final_stage_1._summary is assembler.summary
    assert final_stage_1._memory is assembler.memory
