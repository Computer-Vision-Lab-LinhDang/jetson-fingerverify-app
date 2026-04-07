#!/usr/bin/env python3
"""
Export fingerprint model: PyTorch (.pt) -> ONNX (.onnx) -> TensorRT (.engine)

Model architecture auto-detected from best_eer.pt checkpoint:
  - ViT-Small (embed_dim=384, depth=12, heads=6, patch=14, img=224, RGB)
  - LayerScale (ls1/ls2 per block)
  - 2x GNN layers (graph attention + RPE + FFN)
  - Seed-based attention pooling (4 seeds)
  - MLP head -> 256-dim L2-normalised embedding

Checkpoint structure:
  {epoch, model_state, criterion_state, optimizer_state, val_loss, val_eer, config}

Usage:
  # PT -> ONNX:
  python tools/export_to_trt.py --checkpoint best_eer.pt --onnx models/model.onnx

  # ONNX -> TRT (on Jetson Nano):
  python tools/export_to_trt.py --onnx models/model.onnx --trt models/model_fp16.engine --fp16

  # Full pipeline:
  python tools/export_to_trt.py --checkpoint best_eer.pt --onnx models/model.onnx \
      --trt models/model_fp16.engine --fp16 --validate
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

import torch
import torch.nn as nn
import torch.nn.functional as F


# ====================================================================
# Model Components
# ====================================================================


class PatchEmbed(nn.Module):
    def __init__(self, img_size: int, patch_size: int, in_chans: int, embed_dim: int):
        super().__init__()
        self.num_patches = (img_size // patch_size) ** 2
        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x).flatten(2).transpose(1, 2)


class Attention(nn.Module):
    def __init__(self, dim: int, num_heads: int):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.scale = self.head_dim ** -0.5
        self.qkv = nn.Linear(dim, dim * 3)
        self.proj = nn.Linear(dim, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv.unbind(0)
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        return self.proj(x)


class Mlp(nn.Module):
    def __init__(self, in_features: int, hidden_features: int):
        super().__init__()
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.fc2 = nn.Linear(hidden_features, in_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(F.gelu(self.fc1(x)))


class LayerScale(nn.Module):
    def __init__(self, dim: int, init_values: float = 1e-5):
        super().__init__()
        self.gamma = nn.Parameter(init_values * torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.gamma


class Block(nn.Module):
    """Transformer block with LayerScale (timm-compatible)."""

    def __init__(self, dim: int, num_heads: int, mlp_ratio: float = 4.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = Attention(dim, num_heads)
        self.ls1 = LayerScale(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = Mlp(dim, int(dim * mlp_ratio))
        self.ls2 = LayerScale(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.ls1(self.attn(self.norm1(x)))
        x = x + self.ls2(self.mlp(self.norm2(x)))
        return x


class VisionTransformer(nn.Module):
    """ViT backbone — state_dict keys match timm VisionTransformer."""

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 14,
        in_chans: int = 3,
        embed_dim: int = 384,
        depth: int = 12,
        num_heads: int = 6,
        mlp_ratio: float = 4.0,
    ):
        super().__init__()
        self.patch_embed = PatchEmbed(img_size, patch_size, in_chans, embed_dim)
        num_patches = self.patch_embed.num_patches
        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, embed_dim))
        self.blocks = nn.ModuleList(
            [Block(embed_dim, num_heads, mlp_ratio) for _ in range(depth)]
        )
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B = x.shape[0]
        x = self.patch_embed(x)
        cls = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls, x], dim=1)
        x = x + self.pos_embed
        for blk in self.blocks:
            x = blk(x)
        return self.norm(x)  # [B, 1+N, D]


class ViTBackbone(nn.Module):
    """Wrapper producing 'vit.vit.*' state_dict prefix."""

    def __init__(self, **kwargs):
        super().__init__()
        self.vit = VisionTransformer(**kwargs)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.vit(x)


# ------------------------------------------------------------------
# GNN Layer
# ------------------------------------------------------------------


class GraphAttentionLayer(nn.Module):
    """Multi-head graph attention with relative position encoding."""

    def __init__(
        self, embed_dim: int, num_heads: int,
        rpe_in_dim: int, rpe_hidden_dim: int, ffn_dim: int,
    ):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.scale = self.head_dim ** -0.5

        self.W_q = nn.Linear(embed_dim, embed_dim)
        self.W_k = nn.Linear(embed_dim, embed_dim)
        self.W_v = nn.Linear(embed_dim, embed_dim)
        self.W_o = nn.Linear(embed_dim, embed_dim)

        self.rpe_mlp = nn.Sequential(
            nn.Linear(rpe_in_dim, rpe_hidden_dim),
            nn.ReLU(),
            nn.Linear(rpe_hidden_dim, num_heads),
        )

        self.norm1 = nn.LayerNorm(embed_dim)
        self.norm2 = nn.LayerNorm(embed_dim)

        self.ffn = nn.Sequential(
            nn.Linear(embed_dim, ffn_dim),
            nn.GELU(),
            nn.Dropout(0.0),
            nn.Linear(ffn_dim, embed_dim),
        )

    def forward(self, x: torch.Tensor, rel_pos: torch.Tensor) -> torch.Tensor:
        B, N, D = x.shape
        H, hd = self.num_heads, self.head_dim

        q = self.W_q(x).reshape(B, N, H, hd).permute(0, 2, 1, 3)
        k = self.W_k(x).reshape(B, N, H, hd).permute(0, 2, 1, 3)
        v = self.W_v(x).reshape(B, N, H, hd).permute(0, 2, 1, 3)

        attn = (q @ k.transpose(-2, -1)) * self.scale
        rpe = self.rpe_mlp(rel_pos).permute(0, 3, 1, 2)  # [1, H, N, N]
        attn = attn + rpe
        attn = attn.softmax(dim=-1)

        out = (attn @ v).permute(0, 2, 1, 3).reshape(B, N, D)
        out = self.W_o(out)

        x = self.norm1(x + out)
        x = self.norm2(x + self.ffn(x))
        return x


# ------------------------------------------------------------------
# Seed-based Attention Pooling
# ------------------------------------------------------------------


class SeedPool(nn.Module):
    """Seed-based cross-attention pooling.

    Learnable seed tokens query the input sequence, producing a fixed-size
    output that is projected down to embed_dim.
    """

    def __init__(self, embed_dim: int, num_seeds: int, proj_out_dim: int):
        super().__init__()
        self.seeds = nn.Parameter(torch.randn(num_seeds, embed_dim))
        self.proj = nn.Linear(num_seeds * embed_dim, proj_out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, N, D]
        B, N, D = x.shape
        # seeds: [S, D] -> cross-attention: seeds query x
        attn = torch.matmul(self.seeds, x.transpose(1, 2))  # [S, D] @ [B, D, N] -> [B, S, N]
        attn = (attn / (D ** 0.5)).softmax(dim=-1)
        out = torch.matmul(attn, x)  # [B, S, D]
        out = out.reshape(B, -1)     # [B, S*D]
        return self.proj(out)         # [B, proj_out_dim]


# ------------------------------------------------------------------
# Full Model
# ------------------------------------------------------------------


class FingerprintModel(nn.Module):
    """ViT + GNN + SeedPool + MLP Head -> 256-dim embedding."""

    def __init__(self, cfg: dict):
        super().__init__()
        embed_dim = cfg["embed_dim"]
        img_size = cfg["img_size"]
        patch_size = cfg["patch_size"]
        grid_size = img_size // patch_size

        # ViT backbone
        self.vit = ViTBackbone(
            img_size=img_size, patch_size=patch_size,
            in_chans=cfg["in_chans"], embed_dim=embed_dim,
            depth=cfg["vit_depth"], num_heads=cfg["vit_num_heads"],
            mlp_ratio=cfg["mlp_ratio"],
        )

        # GNN layers
        self.gnn_layers = nn.ModuleList([
            GraphAttentionLayer(
                embed_dim=embed_dim, num_heads=cfg["gnn_num_heads"],
                rpe_in_dim=cfg["rpe_in_dim"], rpe_hidden_dim=cfg["rpe_hidden_dim"],
                ffn_dim=cfg["gnn_ffn_dim"],
            )
            for _ in range(cfg["gnn_depth"])
        ])

        # Seed pooling
        self.pool = SeedPool(embed_dim, cfg["pool_num_seeds"], cfg["pool_proj_out"])

        # Embedding head: Linear -> BN -> ReLU -> Linear -> BN
        self.head = nn.Sequential(
            nn.Linear(cfg["pool_proj_out"], cfg["head_hidden_dim"]),
            nn.BatchNorm1d(cfg["head_hidden_dim"]),
            nn.ReLU(),
            nn.Linear(cfg["head_hidden_dim"], cfg["embedding_dim"]),
            nn.BatchNorm1d(cfg["embedding_dim"]),
        )

        # Training-only (for state_dict compat)
        if cfg.get("num_classes"):
            self.cls_head = nn.Linear(cfg["embedding_dim"], cfg["num_classes"])

        # Pre-compute relative positions for GNN
        self._build_rel_pos(grid_size, cfg["rpe_in_dim"])

    def _build_rel_pos(self, grid_size: int, rpe_dim: int):
        gy, gx = torch.meshgrid(
            torch.arange(grid_size, dtype=torch.float32),
            torch.arange(grid_size, dtype=torch.float32),
            indexing="ij",
        )
        coords = torch.stack([gx.flatten(), gy.flatten()], dim=-1)
        coords = coords / max(grid_size - 1, 1)

        rel = coords.unsqueeze(0) - coords.unsqueeze(1)  # [N, N, 2]
        dist = rel.norm(dim=-1, keepdim=True)
        angle = torch.atan2(rel[..., 1:2], rel[..., 0:1] + 1e-8)

        feats = [rel, dist, angle]
        if rpe_dim >= 5:
            feats.append(torch.sin(angle))
        if rpe_dim >= 6:
            feats.append(torch.cos(angle))

        rel_pos = torch.cat(feats, dim=-1)[..., :rpe_dim]
        self.register_buffer("rel_pos", rel_pos.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [B, 3, 224, 224] RGB fingerprint image.
        Returns:
            [B, 256] L2-normalised embedding.
        """
        tokens = self.vit(x)              # [B, 1+N, D]
        patch_tokens = tokens[:, 1:]      # [B, N, D] exclude CLS

        for gnn in self.gnn_layers:
            patch_tokens = gnn(patch_tokens, self.rel_pos)

        pooled = self.pool(patch_tokens)  # [B, pool_proj_out]
        embedding = self.head(pooled)     # [B, 256]
        return F.normalize(embedding, p=2, dim=-1)


# ====================================================================
# Config detection
# ====================================================================


def detect_config(state_dict: dict[str, torch.Tensor]) -> dict:
    """Auto-detect model config from state_dict tensor shapes."""
    cfg: dict = {}

    # ViT
    cfg["embed_dim"] = state_dict["vit.vit.cls_token"].shape[-1]

    proj_w = state_dict["vit.vit.patch_embed.proj.weight"]
    cfg["patch_size"] = proj_w.shape[2]
    cfg["in_chans"] = proj_w.shape[1]

    num_patches = state_dict["vit.vit.pos_embed"].shape[1] - 1
    grid = int(round(math.sqrt(num_patches)))
    cfg["img_size"] = grid * cfg["patch_size"]

    block_ids = {int(k.split(".")[3]) for k in state_dict if k.startswith("vit.vit.blocks.")}
    cfg["vit_depth"] = max(block_ids) + 1
    cfg["vit_num_heads"] = cfg["embed_dim"] // 64

    fc1_w = state_dict["vit.vit.blocks.0.mlp.fc1.weight"]
    cfg["mlp_ratio"] = fc1_w.shape[0] / cfg["embed_dim"]

    # Check LayerScale
    cfg["has_layer_scale"] = "vit.vit.blocks.0.ls1.gamma" in state_dict

    # GNN
    gnn_ids = {int(k.split(".")[1]) for k in state_dict if k.startswith("gnn_layers.")}
    cfg["gnn_depth"] = (max(gnn_ids) + 1) if gnn_ids else 0

    rpe_w = state_dict.get("gnn_layers.0.rpe_mlp.0.weight")
    if rpe_w is not None:
        cfg["rpe_in_dim"] = rpe_w.shape[1]
        cfg["rpe_hidden_dim"] = rpe_w.shape[0]

    rpe_out = state_dict.get("gnn_layers.0.rpe_mlp.2.weight")
    cfg["gnn_num_heads"] = rpe_out.shape[0] if rpe_out is not None else cfg["vit_num_heads"]

    ffn_w = state_dict.get("gnn_layers.0.ffn.0.weight")
    cfg["gnn_ffn_dim"] = ffn_w.shape[0] if ffn_w is not None else cfg["embed_dim"] * 4

    # Pool
    pool_seeds = state_dict.get("pool.seeds")
    pool_proj_w = state_dict.get("pool.proj.weight")
    cfg["pool_num_seeds"] = pool_seeds.shape[0] if pool_seeds is not None else 4
    cfg["pool_proj_out"] = pool_proj_w.shape[0] if pool_proj_w is not None else cfg["embed_dim"]

    # Head
    head_w = state_dict.get("head.0.weight")
    cfg["head_hidden_dim"] = head_w.shape[0] if head_w is not None else cfg["embed_dim"]

    head_out_w = state_dict.get("head.3.weight")
    cfg["embedding_dim"] = head_out_w.shape[0] if head_out_w is not None else 256

    # Training-only
    cls_w = state_dict.get("cls_head.weight")
    cfg["num_classes"] = cls_w.shape[0] if cls_w is not None else 0

    return cfg


def load_checkpoint(path: str) -> dict[str, torch.Tensor]:
    """Load model state_dict from training checkpoint."""
    logger.info("Loading checkpoint: %s", path)
    ckpt = torch.load(path, map_location="cpu", weights_only=False)

    if isinstance(ckpt, dict):
        # Try known keys in order
        for key in ("model_state", "model_state_dict", "state_dict", "model"):
            if key in ckpt:
                sd = ckpt[key]
                logger.info("  Extracted '%s' from checkpoint.", key)
                # Merge criterion_state if exists (for arcface etc.)
                crit = ckpt.get("criterion_state", {})
                if crit:
                    logger.info("  Merged criterion_state (%d keys).", len(crit))
                    sd.update(crit)
                break
        else:
            sd = ckpt

        # Log training info if available
        if "epoch" in ckpt:
            logger.info("  Epoch: %s, val_eer: %s", ckpt.get("epoch"), ckpt.get("val_eer"))
        if "config" in ckpt:
            logger.info("  Training config: %s", ckpt["config"])
    elif isinstance(ckpt, OrderedDict):
        sd = ckpt
    else:
        raise ValueError(f"Unexpected checkpoint type: {type(ckpt)}")

    # Strip 'module.' prefix from DataParallel
    cleaned = {k.removeprefix("module."): v for k, v in sd.items() if isinstance(v, torch.Tensor)}
    logger.info("  Loaded %d parameter tensors.", len(cleaned))
    return cleaned


# ====================================================================
# ONNX Export
# ====================================================================


def export_onnx(
    model: nn.Module, onnx_path: str,
    img_size: int, in_chans: int, opset: int = 17, batch_size: int = 1,
) -> None:
    model.eval()
    dummy = torch.randn(batch_size, in_chans, img_size, img_size)

    logger.info("Exporting ONNX to %s (opset=%d) ...", onnx_path, opset)
    t0 = time.time()

    torch.onnx.export(
        model, dummy, onnx_path,
        opset_version=opset,
        input_names=["image"],
        output_names=["embedding"],
        dynamo=False,
    )

    elapsed = time.time() - t0
    size_mb = Path(onnx_path).stat().st_size / (1024 * 1024)
    logger.info("  ONNX exported in %.1fs (%.1f MB)", elapsed, size_mb)

    try:
        import onnx
        onnx.checker.check_model(onnx.load(onnx_path))
        logger.info("  ONNX validation passed.")
    except ImportError:
        logger.warning("  'onnx' not installed; skipping validation.")
    except Exception as e:
        logger.error("  ONNX validation failed: %s", e)


# ====================================================================
# ONNX -> TensorRT
# ====================================================================


def convert_to_trt(onnx_path: str, trt_path: str, fp16: bool = True, workspace_mb: int = 1024) -> bool:
    try:
        import tensorrt as trt
    except ImportError:
        logger.error("tensorrt not installed. Run on Jetson Nano with JetPack.")
        return False

    logger.info("TensorRT %s: %s -> %s", trt.__version__, onnx_path, trt_path)

    trt_logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(trt_logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, trt_logger)

    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                logger.error("  Parse error: %s", parser.get_error(i))
            return False

    for i in range(network.num_inputs):
        inp = network.get_input(i)
        logger.info("  Input %d: %s shape=%s", i, inp.name, inp.shape)
    for i in range(network.num_outputs):
        out = network.get_output(i)
        logger.info("  Output %d: %s shape=%s", i, out.name, out.shape)

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_mb << 20)

    if fp16 and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
        logger.info("  FP16 enabled.")

    # Dynamic batch
    profile = builder.create_optimization_profile()
    for i in range(network.num_inputs):
        inp = network.get_input(i)
        shape = inp.shape
        if any(d == -1 for d in shape):
            min_s = tuple(1 if d == -1 else d for d in shape)
            opt_s = tuple(1 if d == -1 else d for d in shape)
            max_s = tuple(8 if d == -1 else d for d in shape)
            profile.set_shape(inp.name, min_s, opt_s, max_s)
    config.add_optimization_profile(profile)

    logger.info("  Building engine (may take several minutes) ...")
    t0 = time.time()
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        logger.error("  TensorRT build failed.")
        return False

    with open(trt_path, "wb") as f:
        f.write(serialized)

    logger.info("  Engine saved: %s (%.1f MB, %.0fs)", trt_path,
                Path(trt_path).stat().st_size / (1024 * 1024), time.time() - t0)
    return True


# ====================================================================
# Validation
# ====================================================================


def validate_pytorch(model: nn.Module, img_size: int, in_chans: int) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        dummy = torch.randn(1, in_chans, img_size, img_size)
        emb = model(dummy).numpy()
    logger.info("  PyTorch OK — shape=%s, L2=%.4f", emb.shape, np.linalg.norm(emb, axis=-1).mean())
    return emb


def validate_onnx(onnx_path: str, img_size: int, in_chans: int) -> np.ndarray | None:
    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("  onnxruntime not installed; skipping.")
        return None

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    dummy = np.random.randn(1, in_chans, img_size, img_size).astype(np.float32)
    emb = sess.run(None, {"image": dummy})[0]
    logger.info("  ONNX OK — shape=%s, L2=%.4f", emb.shape, np.linalg.norm(emb, axis=-1).mean())
    return emb


# ====================================================================
# CLI
# ====================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Export fingerprint model: PT -> ONNX -> TensorRT")
    parser.add_argument("--checkpoint", "-c", default=None, help="PyTorch checkpoint (.pt)")
    parser.add_argument("--onnx", "-o", default=None, help="Output ONNX path")
    parser.add_argument("--trt", "-t", default=None, help="Output TensorRT engine path")
    parser.add_argument("--fp16", action="store_true", default=True)
    parser.add_argument("--fp32", action="store_true")
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--workspace", type=int, default=1024, help="TRT workspace MB")
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if not args.checkpoint and not args.onnx:
        parser.error("Provide --checkpoint or --onnx.")
    if args.trt and not args.onnx:
        parser.error("--trt requires --onnx.")

    # ---- Step 1: PT -> ONNX ----
    if args.checkpoint:
        if not args.onnx:
            args.onnx = str(Path(args.checkpoint).with_suffix(".onnx"))

        Path(args.onnx).parent.mkdir(parents=True, exist_ok=True)

        state_dict = load_checkpoint(args.checkpoint)
        cfg = detect_config(state_dict)

        logger.info("Detected config:")
        for k, v in sorted(cfg.items()):
            logger.info("  %-20s = %s", k, v)

        model = FingerprintModel(cfg)
        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        if missing:
            # Filter out rel_pos buffer (expected to be missing from state_dict)
            real_missing = [k for k in missing if k != "rel_pos"]
            if real_missing:
                logger.warning("Missing keys (%d): %s", len(real_missing), real_missing[:10])
        if unexpected:
            logger.warning("Unexpected keys (%d): %s", len(unexpected), unexpected[:10])

        total = sum(p.numel() for p in model.parameters())
        logger.info("Model: %.2f M params", total / 1e6)

        if args.validate:
            validate_pytorch(model, cfg["img_size"], cfg["in_chans"])

        export_onnx(model, args.onnx, cfg["img_size"], cfg["in_chans"], args.opset, args.batch)

        if args.validate:
            validate_onnx(args.onnx, cfg["img_size"], cfg["in_chans"])

    # ---- Step 2: ONNX -> TRT ----
    if args.trt:
        if not Path(args.onnx).exists():
            logger.error("ONNX not found: %s", args.onnx)
            return 1
        Path(args.trt).parent.mkdir(parents=True, exist_ok=True)
        if not convert_to_trt(args.onnx, args.trt, fp16=not args.fp32, workspace_mb=args.workspace):
            return 1

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
