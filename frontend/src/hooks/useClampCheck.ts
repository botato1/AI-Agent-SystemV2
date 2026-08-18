import { useLayoutEffect, useRef, useState } from "react";

// ref를 붙인 컨테이너 안에서 data-clamp 속성이 달린 요소들을 찾아, line-clamp로 실제
// 잘린 게 있는지(scrollHeight > clientHeight) 감지한다. 컨테이너 자체는 overflow가 없는
// 평범한 div라 직접 측정이 안 되므로, 실제로 line-clamp 클래스가 붙는 개별 요소를 찾아서 잰다.
// "자세히 보기" 버튼을 내용이 실제로 넘칠 때만 보여주기 위해 사용 — 안 그러면 짧은 내용에서
// 눌러도 아무 변화가 없는 의미 없는 버튼이 된다.
export function useClampCheck(deps: unknown[]): [React.RefObject<HTMLDivElement>, boolean] {
  const ref = useRef<HTMLDivElement>(null);
  const [isClamped, setIsClamped] = useState(false);

  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) {
      setIsClamped(false);
      return;
    }
    const targets = container.querySelectorAll<HTMLElement>("[data-clamp]");
    const clamped = Array.from(targets).some((el) => el.scrollHeight - el.clientHeight > 1);
    setIsClamped(clamped);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return [ref, isClamped];
}
