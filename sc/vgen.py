"""vLLM generation backend (config `generation.backend: vllm`), used for every generation step on fast
hardware: number sampling, sender answers, receiver answers. Teacher-forced scoring (log-likelihoods,
top-K targets, margins, the forced-choice probe) and all training stay on transformers.

* The adapter is merged into a copy of the released checkpoint (sc.merge) so vLLM loads it natively.
* Prompts are passed as the exact token ids the transformers path renders (same chat template, same
  thinking setting), and generation stops at the same EOS ids; special tokens are skipped in the text.
* `generation.batch_invariant: true` sets VLLM_BATCH_INVARIANT=1 so outputs do not depend on which other
  requests share a batch (the paired design compares conditions trial by trial).
* Sampling uses one seed per request (seed + request key), so results do not depend on sharding.
Upstream sampled with transformers `generate`; vLLM draws from the same distribution (temperature 1, no
truncation) with different kernels, so individual samples differ from a transformers run.
"""
from __future__ import annotations

import gc
import os

from sc.core import Tok, model_path
from sc.merge import merge_for_vllm


class VGen:
    def __init__(self, cfg, adapter, tk: Tok):
        g = cfg.get("generation", {})
        if g.get("batch_invariant", True):
            os.environ["VLLM_BATCH_INVARIANT"] = "1"
        from vllm import LLM
        self.tk = tk
        self.path = merge_for_vllm(cfg, adapter)
        self.llm = LLM(model=str(self.path), tokenizer=str(model_path(cfg)), dtype="bfloat16", seed=0,
                       gpu_memory_utilization=g.get("vllm_gpu_memory", 0.5), max_model_len=g.get("max_model_len", 4096),
                       limit_mm_per_prompt={"image": 0, "video": 0}, enable_prefix_caching=True,
                       max_num_seqs=g.get("max_num_seqs", 256))

    def vllm_generate(self, prompt_ids, max_new, sample=False, temperature=1.0, seeds=None):
        from vllm import SamplingParams
        from vllm.inputs import TokensPrompt
        seeds = seeds or [None] * len(prompt_ids)
        sps = [SamplingParams(temperature=temperature if sample else 0.0, top_p=1.0, max_tokens=max_new, seed=s,
                              stop_token_ids=self.tk.EOS_IDS, skip_special_tokens=True) for s in seeds]
        outs = self.llm.generate([TokensPrompt(prompt_token_ids=i) for i in prompt_ids], sps, use_tqdm=False)
        return [o.outputs[0].text for o in outs]

    def close(self):
        del self.llm
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


def make_generator(cfg, adapter, tk: Tok, hf_model=None):
    """vLLM engine if generation.backend is vllm, else the transformers model (loaded if not given)."""
    if cfg.get("generation", {}).get("backend", "hf") == "vllm":
        return VGen(cfg, adapter, tk)
    if hf_model is None:
        from sc.core import load_model
        hf_model = load_model(cfg, adapter)
        hf_model.config.use_cache = True
    return hf_model
