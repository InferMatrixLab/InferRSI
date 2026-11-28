"""Record the scheduler steps consumed by the single-device Qwen worker."""


class SamplingTraceExtension:
    def begin_qwen_e2e_trace(self):
        scheduler_type = type(self.model_runner.pipeline.scheduler)
        original_step = scheduler_type.step
        steps = []

        def traced_step(scheduler, model_output, timestep, *args, **kwargs):
            result = original_step(scheduler, model_output, timestep, *args, **kwargs)
            index = scheduler.step_index - 1
            steps.append((timestep, scheduler.sigmas[index:index + 2]))
            return result

        self._qwen_e2e_trace = (scheduler_type, original_step, steps)
        scheduler_type.step = traced_step
        return {"sampling_trace_started": True}

    def end_qwen_e2e_trace(self):
        scheduler_type, original_step, consumed = self._qwen_e2e_trace
        scheduler_type.step = original_step
        del self._qwen_e2e_trace
        steps = [{"timestep": float(timestep), "sigma": float(pair[0]),
                  "next_sigma": float(pair[1])} for timestep, pair in consumed]
        return {"step_count": len(steps), "steps": steps}
