"""Build a contact sheet that binds entities and units to visual references."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import ReferenceBoard
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ReferenceBoardParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    columns: int = Field(default=4, ge=1, le=12)
    thumb_size: int = Field(default=240, ge=80, le=800)


@register_step
class ReferenceBoardStep(BaseStep):
    type = "assets.reference_board"
    status = "available"
    icon = "▦"
    color = "#0ea5e9"
    title = "Reference board"
    description = "Create a contact sheet binding entities and timeline units to images."
    requires = ()
    produces = ("reference_board",)
    params_model = ReferenceBoardParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ReferenceBoardParams.model_validate(params)
        path = context.work / "reference_board.png"
        entries: list[dict[str, object]] = []
        try:
            from PIL import Image, ImageDraw, ImageOps
        except ImportError:  # pragma: no cover - optional dependency
            from videoflow.domain.errors import RecipeError

            raise RecipeError("Pillow is required for assets.reference_board") from None
        files = [Path(item).expanduser() for item in options.paths]
        files = [item for item in files if item.is_file()]
        size = options.thumb_size
        columns = min(options.columns, max(1, len(files)))
        rows = max(1, (len(files) + columns - 1) // columns)
        sheet = Image.new("RGB", (columns * size, rows * (size + 28)), (16, 20, 28))
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(files):
            io.check_cancel()
            try:
                with Image.open(item) as image:
                    thumb = ImageOps.fit(
                        image.convert("RGB"), (size, size), method=Image.Resampling.LANCZOS
                    )
            except OSError:
                continue
            x = (index % columns) * size
            y = (index // columns) * (size + 28)
            sheet.paste(thumb, (x, y))
            label = item.stem[:36]
            draw.text((x + 4, y + size + 5), label, fill=(220, 228, 240))
            entries.append(
                {
                    "index": index,
                    "path": str(item),
                    "label": label,
                    "entity": options.entities[index] if index < len(options.entities) else "",
                    "unit": options.units[index] if index < len(options.units) else "",
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(path)
        board = ReferenceBoard(
            path=str(path),
            entities=list(options.entities),
            units=list(options.units),
            entries=entries,
        )
        json_path = context.work / "reference_board.json"
        json_path.write_text(board.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["reference_board"] = board.model_dump(mode="json")
        context.artifacts["reference_board"] = str(path)
        context.artifacts["reference_board_json"] = str(json_path)
        io.report(100, f"Reference board with {len(entries)} image(s)")
