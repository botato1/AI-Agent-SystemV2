from __future__ import annotations

import argparse
from pathlib import Path

from doc_processor.core.pipeline import DocumentPipeline
from doc_processor.output.assembler import assemble
from doc_processor.output.json_builder import save_json
from doc_processor.output.rag_exporter import save_rag
from doc_processor.output.txt_exporter import save_txt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Document Processor")
    parser.add_argument("--pdf", default="test.pdf", help="입력 PDF 경로")
    parser.add_argument("--out", default="result.json", help="출력 JSON 경로")
    parser.add_argument("--dpi", type=int, default=220, help="렌더링 DPI")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import time
    start = time.time()

    # 1. 파이프라인 실행 → DocumentResult (내부 처리 결과)
    pipeline = DocumentPipeline(dpi=args.dpi)
    doc = pipeline.run(args.pdf)

    # 2. DocumentResult → DocumentSchema (팀 공통 스키마로 변환)
    schema = assemble(doc)

    # 3. 출력
    out = Path(args.out)

    rag_path = save_rag(schema, str(out.with_stem(out.stem + "_rag")))
    print(f"[Done] RAG JSON 저장: {rag_path}")

    elapsed = time.time() - start
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    if minutes > 0:
        print(f"\n[Done] 총 소요 시간: {minutes}분 {seconds:.1f}초")
    else:
        print(f"\n[Done] 총 소요 시간: {seconds:.1f}초")


if __name__ == "__main__":
    main()
