// src/components/HomeView.tsx
import { useEffect, useRef, useState } from "react";
import { useRealMeetings } from "../hooks/useRealMeetings";
import { useRecentMeetings } from "../hooks/useRecentMeetings";
import { useDashboardSummary } from "../hooks/useDashboardSummary";
import { useWorkspaceDecisions } from "../hooks/useWorkspaceDecisions";
import { useContradictions } from "../hooks/useContradictions";
import { getWorkspaceMembersApi, WorkspaceMemberInfo } from "../services/workspace";
import {
  UpcomingMeeting,
  getUpcomingMeetingsApi,
  scheduleMeetingApi,
  updateMeetingInfoApi,
  deleteMeetingApi,
} from "../services/meeting";
import { PlaceholderKey, Task } from "../types";
import {
  MicIcon,
  WarningIcon,
  CloseIcon,
  TrashIcon,
  PencilIcon,
  CheckIcon,
  PersonIcon,
  PlayIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "./icons";
import WelcomeOnboarding from "./WelcomeOnboarding";
import MeetingSearchModal from "./MeetingSearchModal";
import MeetingAttendeesModal from "./MeetingAttendeesModal";
import MeetingExportModal from "./MeetingExportModal";
import ManageMembersModal from "./ManageMembersModal";
import InviteMemberModal from "./InviteMemberModal";
import ContradictionCompareModal from "./ContradictionCompareModal";
import DocumentPreviewModal from "./DocumentPreviewModal";

interface HomeViewProps {
  workspaceId: string;
  userId: string;
  userName: string;
  tasks: Task[];
  onCreateTask: (input: Omit<Task, "id">) => void;
  onUpdateTask: (task: Task) => void;
  onDeleteTask: (id: string) => void;
  onNavigate: (key: PlaceholderKey) => void;
  onOpenMeeting: (meetingId: string) => void;
  onBeginScheduledMeeting: (meetingId: string) => void;
  onOpenDecision: (decisionId: string) => void;
  t: any;
}

interface UpcomingFormData {
  title: string;
  topic: string;
  location: string;
  date: string;
  time: string;
  attendeeIds: string[];
}

type UpcomingKind = "meeting" | "task";
type UpcomingListItem =
  | { kind: "meeting"; sortKey: string; data: UpcomingMeeting }
  | { kind: "task"; sortKey: string; data: Task };

function onboardingStorageKey(userId: string): string {
  return `onboarding_seen_${userId}`;
}

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

function getUpcomingDayLabel(t: any, iso: string): { label: string; isRelative: boolean } {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const target = new Date(iso);
  target.setHours(0, 0, 0, 0);

  const diffTime = target.getTime() - today.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return { label: t.home_day_today, isRelative: true };
  if (diffDays === 1) return { label: t.home_day_tomorrow, isRelative: true };

  return { label: `${target.getMonth() + 1}/${target.getDate()}`, isRelative: false };
}

function formatTimeOnly(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function formatMsToHoursMinutes(ms: number): string {
  if (!ms || ms <= 0) return "0:00";
  const totalMinutes = Math.floor(ms / (1000 * 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

function getThisWeekDateRange(): string {
  const now = new Date();
  const day = now.getDay();
  const diffToMonday = now.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(now.setDate(diffToMonday));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  return `${monday.getMonth() + 1}/${monday.getDate()} - ${sunday.getMonth() + 1}/${sunday.getDate()}`;
}

function weatherLabel(t: any, code: number): string {
  if (code === 0) return t.home_weather_sunny;
  if (code <= 3) return t.home_weather_partly_cloudy;
  if (code === 45 || code === 48) return t.home_weather_fog;
  if (code <= 67 || (code >= 80 && code <= 82)) return t.home_weather_rain;
  if (code <= 77 || code === 85 || code === 86) return t.home_weather_snow;
  if (code >= 95) return t.home_weather_thunderstorm;
  return "-";
}

function ClockAndWeatherWidget({ t }: { t: any }) {
  const [now, setNow] = useState(new Date());
  const [weather, setWeather] = useState<{ temp: number; code: number } | null>(null);
  const [locationName, setLocationName] = useState<string>(t.home_weather_current_location);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000 * 30);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;

    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          if (cancelled) return;
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          fetchLocationAndWeather(lat, lon);
        },
        () => {
          fetchLocationAndWeather(36.3504, 127.3845, t.home_weather_default_city);
        }
      );
    } else {
      fetchLocationAndWeather(36.3504, 127.3845, t.home_weather_default_city);
    }

    async function fetchLocationAndWeather(lat: number, lon: number, defaultName?: string) {
      try {
        if (defaultName) {
          setLocationName(defaultName);
        } else {
          const geoRes = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&accept-language=ko`
          );
          const geoData = await geoRes.json();
          if (!cancelled && geoData?.address) {
            const city =
              geoData.address.city ||
              geoData.address.province ||
              geoData.address.county ||
              geoData.address.town ||
              t.home_weather_current_location;
            setLocationName(city);
          }
        }
      } catch {
        if (!cancelled) setLocationName(t.home_weather_current_location);
      }

      try {
        const weatherRes = await fetch(
          `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true`
        );
        const weatherData = await weatherRes.json();
        if (!cancelled && weatherData?.current_weather) {
          setWeather({
            temp: Math.round(weatherData.current_weather.temperature),
            code: weatherData.current_weather.weathercode,
          });
        }
      } catch {}
    }

    return () => {
      cancelled = true;
    };
  }, []);

  const hours = now.getHours();
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const period = hours >= 12 ? "PM" : "AM";
  const displayHours = hours % 12 || 12;

  return (
    <div className="rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-sm flex items-center justify-between">
      <div>
        <div className="flex items-baseline gap-1">
          <p className="text-3xl font-bold text-recall-text tracking-tight">{displayHours}:{minutes}</p>
          <span className="text-xs font-semibold text-recall-textMuted">{period}</span>
        </div>
      </div>

      <div className="text-right border-l border-recall-border/60 pl-4">
        {weather ? (
          <div>
            <div className="flex items-baseline justify-end gap-1.5">
              <p className="text-xl font-bold text-recall-text">{weather.temp}°</p>
              <span className="text-xs font-medium text-recall-textMuted">{weatherLabel(t, weather.code)}</span>
            </div>
            <p className="text-[11px] text-recall-textMuted mt-0.5 font-medium">📍 {locationName}</p>
          </div>
        ) : (
          <p className="text-xs text-recall-textMuted">{t.home_weather_loading}</p>
        )}
      </div>
    </div>
  );
}

function UpcomingModal({
  workspaceId,
  editingItem,
  onClose,
  onSave,
  t,
}: {
  workspaceId: string;
  editingItem?: { kind: "meeting"; data: UpcomingMeeting } | { kind: "task"; data: Task } | null;
  onClose: () => void;
  onSave: (kind: UpcomingKind, data: UpcomingFormData) => void;
  t: any;
}) {
  const isEditing = !!editingItem;
  const editingMeeting = editingItem?.kind === "meeting" ? editingItem.data : null;
  const editingTask = editingItem?.kind === "task" ? editingItem.data : null;
  const editingTaskDeadline = editingTask?.deadline ? editingTask.deadline.split("T") : null;

  const [kind, setKind] = useState<UpcomingKind>(editingItem?.kind || "meeting");
  const [title, setTitle] = useState(editingMeeting?.title || editingTask?.task || "");
  const [topic, setTopic] = useState(editingMeeting?.topic || "");
  const [location, setLocation] = useState(editingMeeting?.location || "");
  const [date, setDate] = useState(editingTaskDeadline?.[0] || new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState(editingTaskDeadline?.[1] || "15:00");

  const [members, setMembers] = useState<WorkspaceMemberInfo[] | null>(null);
  const [selectedAttendeeIds, setSelectedAttendeeIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (kind !== "meeting") return;
    let cancelled = false;
    async function load() {
      const res = await getWorkspaceMembersApi(workspaceId);
      if (!cancelled && res.status === "success") {
        setMembers(res.members);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, kind]);

  function toggleAttendee(userId: string) {
    setSelectedAttendeeIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }

  function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    const needsDateTime = kind === "task" || !isEditing;
    if (!title.trim() || (needsDateTime && (!date || !time))) return;
    onSave(kind, {
      title: title.trim(),
      topic: topic.trim(),
      location: location.trim(),
      date,
      time,
      attendeeIds: Array.from(selectedAttendeeIds),
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-lg font-bold text-recall-text">
            {isEditing ? t.home_upcoming_modal_edit_title : t.home_upcoming_modal_add_title}
          </p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text transition">
            <CloseIcon size={18} />
          </button>
        </div>

        {!isEditing && (
          <div className="mb-4 flex gap-1 rounded-xl border border-recall-border bg-recall-bgSoft p-1">
            <button
              type="button"
              onClick={() => setKind("meeting")}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold transition ${
                kind === "meeting" ? "bg-recall-accent text-white" : "text-recall-textMuted hover:text-recall-text"
              }`}
            >
              {t.home_upcoming_kind_meeting}
            </button>
            <button
              type="button"
              onClick={() => setKind("task")}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold transition ${
                kind === "task" ? "bg-recall-accent text-white" : "text-recall-textMuted hover:text-recall-text"
              }`}
            >
              {t.home_upcoming_kind_task}
            </button>
          </div>
        )}

        <form onSubmit={handleFormSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
              {t.home_upcoming_field_title} <span className="text-recall-danger">*</span>
            </label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={kind === "meeting" ? t.home_upcoming_placeholder_meeting : t.home_upcoming_placeholder_task}
              className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text outline-none focus:border-recall-accent transition font-medium"
            />
          </div>

          {kind === "meeting" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
                  {t.home_upcoming_field_topic}
                </label>
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder={t.home_upcoming_optional_placeholder}
                  className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3 py-2.5 text-xs text-recall-text outline-none focus:border-recall-accent transition"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
                  {t.meeting_minutes_location_label}
                </label>
                <input
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder={t.home_upcoming_optional_placeholder}
                  className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3 py-2.5 text-xs text-recall-text outline-none focus:border-recall-accent transition"
                />
              </div>
            </div>
          )}

          {kind === "meeting" && isEditing ? (
            <p className="rounded-xl border border-recall-border/60 bg-recall-bgSoft px-3.5 py-2.5 text-xs text-recall-textMuted">
              {t.home_upcoming_edit_notice}
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
                  {t.home_upcoming_field_date}
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3 py-2.5 text-xs text-recall-text outline-none focus:border-recall-accent transition"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
                  {t.home_upcoming_field_time}
                </label>
                <input
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3 py-2.5 text-xs text-recall-text outline-none focus:border-recall-accent transition"
                />
              </div>
            </div>
          )}

          {kind === "meeting" && !isEditing && (
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
                {t.home_upcoming_field_attendees}
              </label>
              <div className="max-h-32 space-y-0.5 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft p-1.5">
                {members === null ? (
                  <p className="p-2 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
                ) : members.length === 0 ? (
                  <p className="p-2 text-center text-xs text-recall-textMuted">{t.home_upcoming_no_members}</p>
                ) : (
                  members.map((m) => {
                    const name = m.display_name || m.username;
                    const isSelected = selectedAttendeeIds.has(m.user_id);
                    return (
                      <button
                        key={m.user_id}
                        type="button"
                        onClick={() => toggleAttendee(m.user_id)}
                        className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs hover:bg-white/5 transition"
                      >
                        <span className="font-medium text-recall-text">{name}</span>
                        {isSelected && <CheckIcon size={14} className="text-recall-accent flex-shrink-0" />}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}

          <div className="mt-6 flex justify-end gap-2 border-t border-recall-border pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition"
            >
              {t.task_cancel}
            </button>
            <button
              type="submit"
              disabled={!title.trim()}
              className="rounded-xl bg-recall-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition shadow-md shadow-recall-accent/20"
            >
              {isEditing ? t.home_upcoming_save_edit : t.home_upcoming_save_new}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SelectExportMeetingModal({
  workspaceId,
  onClose,
  onSelect,
  t,
}: {
  workspaceId: string;
  onClose: () => void;
  onSelect: (meetingId: string) => void;
  t: any;
}) {
  const { recentMeetings, isLoading } = useRecentMeetings(workspaceId, 20);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-lg font-bold text-recall-text">{t.home_export_select_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text transition">
            <CloseIcon size={18} />
          </button>
        </div>

        {isLoading ? (
          <p className="py-8 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
        ) : recentMeetings.length === 0 ? (
          <p className="py-8 text-center text-xs text-recall-textMuted">{t.home_export_select_empty}</p>
        ) : (
          <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
            {recentMeetings.map((m) => (
              <button
                key={m.id}
                onClick={() => onSelect(m.id)}
                className="flex w-full items-center justify-between rounded-xl border border-recall-border/60 bg-recall-bgSoft p-3 text-left hover:border-recall-accent/60 transition group"
              >
                <span className="truncate text-sm font-bold text-recall-text group-hover:text-recall-accent">
                  {m.title}
                </span>
                <span className="text-xs text-recall-textMuted flex-shrink-0 ml-2">
                  {m.started_at ? formatShortDate(m.started_at) : "-"}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function HomeView({
  workspaceId,
  userId,
  userName,
  tasks,
  onCreateTask,
  onUpdateTask,
  onDeleteTask,
  onNavigate,
  onOpenMeeting,
  onBeginScheduledMeeting,
  onOpenDecision,
  t,
}: HomeViewProps) {
  const [hasSeenOnboarding, setHasSeenOnboarding] = useState(
    () => localStorage.getItem(onboardingStorageKey(userId)) === "1"
  );

  const { meetings } = useRealMeetings(workspaceId);
  const { recentMeetings, isLoading: isRecentLoading } = useRecentMeetings(workspaceId, 4);
  const { summary: dashboardSummary, reload: reloadDashboardSummary } = useDashboardSummary(workspaceId);
  const {
    contradictions: unresolvedContradictions,
    resolve: resolveContradiction,
    update: updateContradiction,
  } = useContradictions(workspaceId);
  // 화살표로 하나씩 넘겨보는 캐러셀 인덱스. 목록이 줄어들면(처리/삭제) 범위를 벗어날 수 있어서
  // 항상 clampedReviewIndex를 통해서만 읽는다.
  const [reviewIndex, setReviewIndex] = useState(0);
  const [compareContradictionId, setCompareContradictionId] = useState<string | null>(null);
  const [referenceDocPreview, setReferenceDocPreview] = useState<{ id: string; name: string } | null>(null);
  const clampedReviewIndex =
    unresolvedContradictions.length === 0 ? 0 : Math.min(reviewIndex, unresolvedContradictions.length - 1);
  const visibleContradiction = unresolvedContradictions[clampedReviewIndex] ?? null;
  const compareContradiction =
    unresolvedContradictions.find((c) => c.id === compareContradictionId) ?? null;

  function goToPrevReview() {
    setReviewIndex(Math.max(0, clampedReviewIndex - 1));
  }
  function goToNextReview() {
    setReviewIndex(Math.min(unresolvedContradictions.length - 1, clampedReviewIndex + 1));
  }

  const [upcoming, setUpcoming] = useState<UpcomingMeeting[]>([]);
  const [showUpcomingModal, setShowUpcomingModal] = useState(false);
  const [editingItem, setEditingItem] = useState<
    { kind: "meeting"; data: UpcomingMeeting } | { kind: "task"; data: Task } | null
  >(null);

  const [showSearchModal, setShowSearchModal] = useState(false);
  const [showManageMembersModal, setShowManageMembersModal] = useState(false);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showSelectExportModal, setShowSelectExportModal] = useState(false);
  const [selectedExportMeetingId, setSelectedExportMeetingId] = useState<string | null>(null);

  async function loadUpcoming() {
    const res = await getUpcomingMeetingsApi(workspaceId);
    if (res.status === "success") setUpcoming(res.meetings);
  }

  useEffect(() => {
    loadUpcoming();
  }, [workspaceId]);

  if (!hasSeenOnboarding) {
    return (
      <WelcomeOnboarding
        userName={userName}
        t={t}
        onDone={() => {
          localStorage.setItem(onboardingStorageKey(userId), "1");
          setHasSeenOnboarding(true);
        }}
      />
    );
  }

  async function handleSaveUpcoming(kind: UpcomingKind, data: UpcomingFormData) {
    if (kind === "task") {
      const deadline = `${data.date}T${data.time}`;
      if (editingItem?.kind === "task") {
        onUpdateTask({ ...editingItem.data, task: data.title, deadline });
      } else {
        onCreateTask({
          task: data.title,
          description: null,
          assignee: null,
          deadline,
          status: "todo",
          priority: "medium",
        });
      }
    } else if (editingItem?.kind === "meeting") {
      const res = await updateMeetingInfoApi(workspaceId, editingItem.data.id, {
        title: data.title,
        topic: data.topic,
        location: data.location,
      });
      if (res.status !== "success") {
        alert(res.message);
        return;
      }
      await loadUpcoming();
    } else {
      const scheduledAt = new Date(`${data.date}T${data.time}:00`).toISOString();
      const res = await scheduleMeetingApi(workspaceId, {
        title: data.title,
        topic: data.topic,
        location: data.location,
        scheduled_at: scheduledAt,
        attendee_ids: data.attendeeIds,
      });
      if (res.status !== "success") {
        alert(res.message);
        return;
      }
      await loadUpcoming();
    }

    setShowUpcomingModal(false);
    setEditingItem(null);
  }

  async function handleRemoveUpcoming(item: UpcomingListItem) {
    if (item.kind === "task") {
      onDeleteTask(item.data.id);
      return;
    }
    const res = await deleteMeetingApi(workspaceId, item.data.id);
    if (res.status === "success") {
      setUpcoming((prev) => prev.filter((u) => u.id !== item.data.id));
    } else {
      alert(res.message);
    }
  }

  function handleBeginUpcoming(id: string) {
    setUpcoming((prev) => prev.filter((u) => u.id !== id));
    onBeginScheduledMeeting(id);
  }

  // 마감일이 지정돼 있고 아직 완료 안 된 할 일만 "예정된 회의" 목록에 같이 보여준다
  const upcomingTasks = tasks.filter((t) => t.deadline && t.status !== "done");

  const upcomingListItems: UpcomingListItem[] = [
    ...upcoming.map((m): UpcomingListItem => ({ kind: "meeting", sortKey: m.scheduled_at, data: m })),
    ...upcomingTasks.map((t): UpcomingListItem => ({ kind: "task", sortKey: t.deadline as string, data: t })),
    // 회의(scheduled_at)는 UTC ISO 문자열, 할일(deadline)은 로컬 시간 문자열(Z 없음)이라
    // 문자열 그대로 비교하면 형식이 달라 순서가 어긋난다 - 실제 시각(ms)으로 비교해야 한다.
  ].sort((a, b) => new Date(a.sortKey).getTime() - new Date(b.sortKey).getTime());

  const now = new Date();

  return (
    <div className="h-full w-full overflow-y-auto bg-recall-bgMain custom-scrollbar">
      {/* 상단 배너 */}
      <div className="relative border-b border-recall-border">
        <div className="relative h-28 overflow-hidden bg-[linear-gradient(180deg,#dbe9fd_0%,#bcd7fb_100%)] dark:bg-[linear-gradient(180deg,#132241_0%,#0d1a30_100%)] dark:opacity-80">
          <svg
            className="absolute inset-y-0 left-0 h-full w-[200%]"
            style={{ animation: "recall-wave-drift 28s linear infinite" }}
            viewBox="0 0 1800 112"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              d="M0,70 C100,30 200,110 300,70 C400,30 500,110 600,70 C700,30 800,110 900,70 C1000,30 1100,110 1200,70 C1300,30 1400,110 1500,70 C1600,30 1700,110 1800,70 L1800,112 L0,112 Z"
              fill="#eaf2fe"
              opacity="0.6"
            />
            <path
              d="M0,55 C100,90 200,20 300,55 C400,90 500,20 600,55 C700,90 800,20 900,55 C1000,90 1100,20 1200,55 C1300,90 1400,20 1500,55 C1600,90 1700,20 1800,55"
              fill="none"
              stroke="#3b82f6"
              strokeWidth="1.5"
              opacity="0.55"
            />
          </svg>
        </div>

        <div className="w-full px-12">
          <p className="pt-4 text-xs font-semibold uppercase tracking-wide text-recall-textMuted">{t.home_banner_eyebrow}</p>
          <p className="mt-1 text-2xl font-bold text-recall-text">Re:Call</p>
          <p className="mt-1.5 max-w-xl text-sm text-recall-textMuted">{t.home_tagline}</p>
          <p className="mt-3 text-xs text-recall-textMuted">
            {t.home_stats_total_meetings(dashboardSummary?.total_meeting_count ?? 0)}
            {" · "}
            {t.home_stats_member_count(dashboardSummary?.member_count ?? 0)}
            {dashboardSummary?.last_meeting_at
              ? ` · ${t.home_stats_last_meeting(formatDateTime(dashboardSummary.last_meeting_at))}`
              : ""}
          </p>
        </div>
        <div className="pb-6" />
      </div>

      <div className="w-full px-8 py-6">
        {/* 🌟 15% 진함 정도의 딱 알맞고 은은한 그라데이션 배경 + 전진 배치된 버튼 */}
        <div
          onClick={() => onNavigate("voiceMeeting")}
          className="group relative mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 rounded-2xl border border-recall-accent/20 bg-gradient-to-r from-recall-accent/15 via-recall-accent/5 to-transparent p-6 shadow-sm hover:border-recall-accent/50 transition-all cursor-pointer active:scale-[0.99]"
        >
          <div className="flex-1 min-w-0">
            <h2 className="text-xl sm:text-2xl font-bold text-recall-text">
              {t.home_start_card_greeting(userName)}
            </h2>
            <p className="text-xs sm:text-sm text-recall-textMuted mt-1.5 leading-relaxed">
              {t.home_start_card_desc}
            </p>
          </div>

          <button
            onClick={(e) => {
              e.stopPropagation();
              onNavigate("voiceMeeting");
            }}
            className="flex items-center gap-2.5 rounded-xl bg-recall-accent px-6 py-3.5 text-sm sm:text-base font-bold text-white hover:opacity-95 transition shadow-md shadow-recall-accent/20 group-hover:translate-x-1 shrink-0"
          >
            <MicIcon size={18} />
            <span>{t.home_start_meeting}</span>
            <span>→</span>
          </button>
        </div>

        {/* 3열 대시보드 레이아웃 */}
        <div className="grid grid-cols-12 gap-4">
          
          {/* 1열 (왼쪽): 예정된 회의 + 확인이 필요한 부분 */}
          <div className="col-span-3 space-y-4">
            
            {/* 예정된 회의 */}
            <div className="rounded-2xl border border-recall-border bg-recall-bg p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between border-b border-recall-border/60 pb-2">
                <p className="text-base font-bold text-recall-text">{t.home_upcoming_title}</p>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-recall-textMuted">
                    {t.home_month_label(now.getFullYear(), now.getMonth() + 1)}
                  </span>
                  <button
                    onClick={() => {
                      setEditingItem(null);
                      setShowUpcomingModal(true);
                    }}
                    className="text-xs font-semibold text-recall-accent hover:underline"
                  >
                    {t.home_upcoming_add}
                  </button>
                </div>
              </div>

              {upcomingListItems.length === 0 ? (
                <p className="py-6 text-center text-xs text-recall-textMuted">{t.home_upcoming_empty}</p>
              ) : (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-0.5">
                  {upcomingListItems.map((item) => {
                    const isMeeting = item.kind === "meeting";
                    const iso = isMeeting ? item.data.scheduled_at : (item.data.deadline as string);
                    const dayInfo = getUpcomingDayLabel(t, iso);
                    const itemTitle = isMeeting ? item.data.title : item.data.task;
                    const subLabel = isMeeting
                      ? item.data.attendees.map((a) => a.display_name).join(", ") || t.home_upcoming_no_attendees
                      : t.home_upcoming_task_label;
                    return (
                      <div
                        key={`${item.kind}-${item.data.id}`}
                        className="group relative flex items-center justify-between rounded-xl border border-recall-border/70 bg-recall-bgSoft p-2.5 transition hover:border-recall-accent/50"
                      >
                        <div className="w-10 flex-shrink-0">
                          <p className={`text-xs font-bold ${dayInfo.isRelative ? "text-amber-500" : "text-recall-textMuted"}`}>
                            {dayInfo.label}
                          </p>
                          <p className="text-[10px] text-recall-textMuted mt-0.5">{formatTimeOnly(iso)}</p>
                        </div>

                        <div className="min-w-0 flex-1 pl-2">
                          <p className="truncate text-xs font-bold text-recall-text" title={itemTitle}>
                            {itemTitle}
                          </p>
                          <p className="truncate text-[10px] text-recall-textMuted mt-0.5" title={subLabel}>
                            {subLabel}
                          </p>
                        </div>

                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 ml-1 flex-shrink-0">
                          {isMeeting && (
                            <button
                              onClick={() => handleBeginUpcoming(item.data.id)}
                              className="text-recall-textMuted hover:text-emerald-500 transition"
                              title={t.home_upcoming_start_now}
                            >
                              <PlayIcon size={12} />
                            </button>
                          )}
                          <button
                            onClick={() => {
                              setEditingItem(item);
                              setShowUpcomingModal(true);
                            }}
                            className="text-recall-textMuted hover:text-recall-accent transition"
                            title={t.meeting_export_edit}
                          >
                            <PencilIcon size={12} />
                          </button>
                          <button
                            onClick={() => handleRemoveUpcoming(item)}
                            className="text-recall-textMuted hover:text-recall-danger transition"
                            title={t.task_delete}
                          >
                            <TrashIcon size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 확인이 필요한 부분 */}
            <div className="rounded-2xl border border-recall-border bg-recall-bg p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between border-b border-recall-border/60 pb-2">
                <p className="text-base font-bold text-recall-text">
                  {t.home_review_title}
                </p>
                {unresolvedContradictions.length > 0 && (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400">
                    {t.home_review_pending_count(unresolvedContradictions.length)}
                  </span>
                )}
              </div>

              {!visibleContradiction ? (
                <p className="py-6 text-center text-xs text-recall-textMuted">{t.home_review_empty}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={goToPrevReview}
                      disabled={clampedReviewIndex === 0}
                      aria-label={t.home_review_prev}
                      className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-recall-border text-recall-textMuted transition hover:bg-white/5 disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronLeftIcon size={14} />
                    </button>

                    <div className="flex flex-1 flex-col gap-2.5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3.5">
                      <p className="text-xs text-recall-text leading-relaxed font-medium">
                        {visibleContradiction.display_message || visibleContradiction.statement_text_snapshot}
                      </p>

                      <p className="text-[11px] text-recall-textMuted">
                        {visibleContradiction.reference_source_name || t.home_review_default_source} ·{" "}
                        {formatShortDate(visibleContradiction.detected_at)}
                      </p>

                      <div className="pt-1 border-t border-amber-500/10">
                        <button
                          onClick={() => setCompareContradictionId(visibleContradiction.id)}
                          className="w-full rounded-lg border border-recall-border bg-recall-bgSoft py-1.5 text-xs font-semibold text-recall-text hover:bg-white/10 transition text-center"
                        >
                          {t.contradiction_compare_title}
                        </button>
                      </div>
                    </div>

                    <button
                      onClick={goToNextReview}
                      disabled={clampedReviewIndex === unresolvedContradictions.length - 1}
                      aria-label={t.home_review_next}
                      className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-recall-border text-recall-textMuted transition hover:bg-white/5 disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronRightIcon size={14} />
                    </button>
                  </div>

                  {unresolvedContradictions.length > 1 && (
                    <p className="text-center text-[11px] text-recall-textMuted">
                      {clampedReviewIndex + 1} / {unresolvedContradictions.length}
                    </p>
                  )}
                </div>
              )}
            </div>

          </div>

          {/* 2열 (중앙): 최근 회의록 */}
          <div className="col-span-5">
            <div className="rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-sm h-full flex flex-col justify-between">
              <div>
                <div className="mb-4 flex items-center justify-between border-b border-recall-border/60 pb-3">
                  <p className="text-base font-bold text-recall-text">
                    {t.home_recent_title}
                  </p>
                  <button
                    onClick={() => onNavigate("voiceMeeting")}
                    className="text-xs font-semibold text-recall-textMuted hover:text-recall-text"
                  >
                    {t.home_recent_view_all(recentMeetings.length)}
                  </button>
                </div>

                {isRecentLoading ? (
                  <p className="py-12 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
                ) : recentMeetings.length === 0 ? (
                  <p className="py-12 text-center text-sm text-recall-textMuted">{t.home_recent_empty}</p>
                ) : (
                  <div className="space-y-3">
                    {recentMeetings.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => onOpenMeeting(m.id)}
                        className="flex w-full flex-col gap-1.5 rounded-xl border border-recall-border/60 bg-recall-bgSoft p-3.5 text-left hover:border-recall-accent/60 transition group"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-base font-bold text-recall-text group-hover:text-recall-accent transition">
                            {m.title}
                          </span>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            {m.contradiction_count === 0 ? (
                              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                                {t.home_recent_clean_badge}
                              </span>
                            ) : (
                              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                                {t.home_recent_contradiction_badge(m.contradiction_count)}
                              </span>
                            )}
                            <span className="text-xs text-recall-textMuted font-medium">
                              {m.started_at ? formatShortDate(m.started_at) : "-"}
                            </span>
                          </div>
                        </div>

                        {m.preview && (
                          <p className="line-clamp-2 text-xs text-recall-textMuted/90 leading-relaxed mt-0.5">
                            {m.preview}
                          </p>
                        )}

                        <div className="flex items-center gap-1 text-xs text-recall-textMuted mt-1">
                          <PersonIcon size={12} />
                          <span>{t.home_recent_attendee_count(m.attendee_count)}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 3열 (오른쪽): 현재시각+날씨 / 바로 가기 / 이번 주 요약 */}
          <div className="col-span-4 space-y-4">
            
            <ClockAndWeatherWidget t={t} />

            <div className="rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-sm">
              <p className="mb-3 text-base font-bold text-recall-text">{t.home_quick_actions_title}</p>

              <div className="divide-y divide-recall-border/60 border-t border-recall-border/60 text-sm">
                <button
                  onClick={() => setShowSearchModal(true)}
                  className="flex w-full items-center justify-between py-3 px-1 text-left text-recall-text hover:bg-white/5 transition rounded-lg group"
                >
                  <div className="flex items-center gap-2.5 font-semibold group-hover:text-recall-accent transition">
                    <span className="text-base">🔍</span>
                    <span>{t.home_quick_search}</span>
                  </div>
                </button>

                <button
                  onClick={() => setShowManageMembersModal(true)}
                  className="flex w-full items-center justify-between py-3 px-1 text-left text-recall-text hover:bg-white/5 transition rounded-lg group"
                >
                  <div className="flex items-center gap-2.5 font-semibold group-hover:text-recall-accent transition">
                    <span className="text-base">👥</span>
                    <span>{t.settings_member_count}</span>
                  </div>
                  {dashboardSummary?.member_count && (
                    <span className="text-xs text-recall-textMuted font-medium">
                      {dashboardSummary.member_count}
                    </span>
                  )}
                </button>

                <button
                  onClick={() => setShowSelectExportModal(true)}
                  className="flex w-full items-center justify-between py-3 px-1 text-left text-recall-text hover:bg-white/5 transition rounded-lg group"
                >
                  <div className="flex items-center gap-2.5 font-semibold group-hover:text-recall-accent transition">
                    <span className="text-base">📄</span>
                    <span>{t.meeting_export_title}</span>
                  </div>
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between border-b border-recall-border/60 pb-3">
                <p className="text-base font-bold text-recall-text">{t.home_week_plain_title}</p>
                <span className="text-xs text-recall-textMuted font-medium">
                  {getThisWeekDateRange()}
                </span>
              </div>

              <div className="grid grid-cols-3 divide-x divide-recall-border/60 border border-recall-border/60 rounded-xl overflow-hidden bg-recall-bgSoft">
                <div className="p-3.5 flex flex-col justify-between text-center">
                  <p className="text-2xl font-bold text-recall-text">
                    {dashboardSummary?.week_meeting_count ?? 0}
                  </p>
                  <p className="text-xs text-recall-textMuted font-medium mt-2">{t.home_week_meetings}</p>
                </div>

                <div className="p-3.5 flex flex-col justify-between text-center">
                  <p className="text-2xl font-bold text-recall-text">
                    {formatMsToHoursMinutes(dashboardSummary?.week_duration_ms ?? 0)}
                  </p>
                  <p className="text-xs text-recall-textMuted font-medium mt-2">{t.home_week_recorded_time}</p>
                </div>

                <div className="p-3.5 flex flex-col justify-between text-center">
                  <p className="text-2xl font-bold text-recall-danger">
                    {dashboardSummary?.week_contradiction_count ?? 0}
                  </p>
                  <p className="text-xs text-recall-textMuted font-medium mt-2">{t.home_week_missed_contradictions}</p>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {showUpcomingModal && (
        <UpcomingModal
          workspaceId={workspaceId}
          editingItem={editingItem}
          onClose={() => {
            setShowUpcomingModal(false);
            setEditingItem(null);
          }}
          onSave={handleSaveUpcoming}
          t={t}
        />
      )}

      {showSearchModal && (
        <MeetingSearchModal
          workspaceId={workspaceId}
          onClose={() => setShowSearchModal(false)}
          onSelectMeeting={() => onNavigate("voiceMeeting")}
          t={t}
        />
      )}

      {showManageMembersModal && (
        <ManageMembersModal
          workspaceId={workspaceId}
          workspaceName={t.workspace_current_name}
          currentUserId={userId}
          onClose={() => setShowManageMembersModal(false)}
          onOpenInviteModal={() => setShowInviteModal(true)}
          onMembersChanged={reloadDashboardSummary}
          t={t}
        />
      )}

      {showInviteModal && (
        <InviteMemberModal
          workspaceId={workspaceId}
          workspaceName={t.workspace_current_name}
          onClose={() => setShowInviteModal(false)}
          onMembersChanged={reloadDashboardSummary}
        />
      )}

      {showSelectExportModal && (
        <SelectExportMeetingModal
          workspaceId={workspaceId}
          onClose={() => setShowSelectExportModal(false)}
          onSelect={(meetingId) => {
            setShowSelectExportModal(false);
            setSelectedExportMeetingId(meetingId);
          }}
          t={t}
        />
      )}

      {selectedExportMeetingId && (
        <MeetingExportModal
          workspaceId={workspaceId}
          meetingId={selectedExportMeetingId}
          onClose={() => setSelectedExportMeetingId(null)}
          t={t}
        />
      )}

      {compareContradiction && (
        <ContradictionCompareModal
          contradiction={compareContradiction}
          onClose={() => setCompareContradictionId(null)}
          onResolve={(id, resolutionType, newDecisionText, newDecisionReason) => {
            resolveContradiction(id, resolutionType, undefined, newDecisionText, newDecisionReason);
            setCompareContradictionId(null);
          }}
          onUpdate={updateContradiction}
          onViewInMeeting={
            compareContradiction.source_type === "meeting_segment"
              ? () => {
                  setCompareContradictionId(null);
                  // meeting_id가 내려오면 그 회의를 바로 열고, 아직 없으면(구버전 응답)
                  // 예전처럼 회의 목록 화면으로만 이동한다.
                  if (compareContradiction.meeting_id) {
                    onOpenMeeting(compareContradiction.meeting_id);
                  } else {
                    onNavigate("voiceMeeting");
                  }
                }
              : undefined
          }
          onViewReference={
            compareContradiction.reference_type === "content_chunk"
              ? () =>
                  setReferenceDocPreview({
                    id: compareContradiction.reference_file_id,
                    name: compareContradiction.reference_source_name || t.home_review_default_source,
                  })
              : undefined
          }
          onViewDecision={
            compareContradiction.reference_type === "decision" && compareContradiction.reference_decision_id
              ? () => {
                  setCompareContradictionId(null);
                  onOpenDecision(compareContradiction.reference_decision_id!);
                }
              : undefined
          }
          t={t}
        />
      )}

      {referenceDocPreview && (
        <DocumentPreviewModal
          workspaceId={workspaceId}
          documentId={referenceDocPreview.id}
          documentName={referenceDocPreview.name}
          onClose={() => setReferenceDocPreview(null)}
          t={t}
        />
      )}
    </div>
  );
}