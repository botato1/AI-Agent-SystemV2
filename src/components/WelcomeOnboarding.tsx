import { useState } from "react";
import { MicIcon, CheckIcon, WarningIcon, ChevronRightIcon } from "./icons";

interface WelcomeOnboardingProps {
  userName: string;
  onDone: () => void;
  t: any;
}

const TUTORIAL_STEPS = [
  { icon: MicIcon, titleKey: "onboarding_step1_title", bodyKey: "onboarding_step1_body" },
  { icon: CheckIcon, titleKey: "onboarding_step2_title", bodyKey: "onboarding_step2_body" },
  { icon: WarningIcon, titleKey: "onboarding_step3_title", bodyKey: "onboarding_step3_body" },
] as const;

export default function WelcomeOnboarding({ userName, onDone, t }: WelcomeOnboardingProps) {
  const [stage, setStage] = useState<"welcome" | "tutorial">("welcome");
  const [stepIndex, setStepIndex] = useState(0);

  if (stage === "welcome") {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-6 bg-recall-bgMain p-6 text-center">
        <div>
          <p className="text-2xl font-bold text-recall-text">{t.onboarding_welcome_title(userName)}</p>
          <p className="mt-2 text-base text-recall-textMuted">{t.onboarding_welcome_body}</p>
        </div>
        <button
          onClick={() => setStage("tutorial")}
          className="rounded-xl bg-recall-accent px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition"
        >
          {t.onboarding_welcome_cta}
        </button>
        <button onClick={onDone} className="text-sm text-recall-textMuted hover:text-recall-text transition">
          {t.onboarding_skip}
        </button>
      </div>
    );
  }

  const step = TUTORIAL_STEPS[stepIndex];
  const StepIcon = step.icon;
  const isLastStep = stepIndex === TUTORIAL_STEPS.length - 1;

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-6 bg-recall-bgMain p-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-recall-accent/10 text-recall-accent">
        <StepIcon size={28} />
      </div>
      <div>
        <p className="text-xl font-bold text-recall-text">{t[step.titleKey]}</p>
        <p className="mt-2 max-w-sm text-base text-recall-textMuted">{t[step.bodyKey]}</p>
      </div>

      <div className="flex gap-1.5">
        {TUTORIAL_STEPS.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 w-1.5 rounded-full ${i === stepIndex ? "bg-recall-accent" : "bg-recall-border"}`}
          />
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button onClick={onDone} className="text-sm text-recall-textMuted hover:text-recall-text transition">
          {t.onboarding_skip}
        </button>
        <button
          onClick={() => (isLastStep ? onDone() : setStepIndex((i) => i + 1))}
          className="flex items-center gap-1 rounded-xl bg-recall-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition"
        >
          {isLastStep ? t.onboarding_finish : t.onboarding_next}
          {!isLastStep && <ChevronRightIcon size={14} />}
        </button>
      </div>
    </div>
  );
}
