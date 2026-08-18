import { useEffect, useRef, useState } from "react";
import { getWorkspaceMembersApi, WorkspaceMemberInfo } from "../services/workspace";
import { getVoiceProfileListApi } from "../services/voice";
import { RecordingMode } from "../services/meeting";
import { Category } from "../services/category";
import { CloseIcon, ChevronDownIcon, CheckIcon, MicIcon } from "./icons";

const CREATE_CATEGORY_VALUE = "__create__";

interface MeetingStartModalProps {
  workspaceId: string;
  currentUserId: string;
  defaultTitle: string;
  onClose: () => void;
  onStart: (
    title: string,
    attendeeIds: string[],
    location?: string,
    recordingMode?: RecordingMode,
    categoryId?: string
  ) => void;
  t: any;
  // 카테고리 목록. 아직 백엔드 카테고리 API가 없으면 빈 배열로 넘기면 된다 -
  // 그 경우 드롭다운은 숨겨지고 지금처럼 카테고리 없이 시작된다.
  categories?: Category[];
  // 회의를 카테고리 폴더 안에서 시작한 경우 (경로 1) — 값이 있으면 드롭다운 대신
  // 고정된 라벨만 보여주고 매번 고를 필요가 없다.
  lockedCategory?: Category | null;
  // 전체 화면에서 시작한 경우 (경로 2) 기본으로 선택해둘 카테고리
  suggestedCategoryId?: string | null;
  onCreateCategory?: (name: string) => Promise<Category | null>;
}

function generatePrettyDefaultTitle(t: any): string {
  const now = new Date();
  const month = now.getMonth() + 1;
  const date = now.getDate();
  const hours = now.getHours();
  const minutes = now.getMinutes();

  const timePeriod = hours < 12 ? t.meeting_am : t.meeting_pm;
  const displayHours = hours % 12 === 0 ? 12 : hours % 12;
  const displayMinutes = String(minutes).padStart(2, "0");

  return t.meeting_default_pretty_title(month, date, timePeriod, displayHours, displayMinutes);
}

export default function MeetingStartModal({
  workspaceId,
  currentUserId,
  defaultTitle,
  onClose,
  onStart,
  t,
  categories = [],
  lockedCategory = null,
  suggestedCategoryId = null,
  onCreateCategory,
}: MeetingStartModalProps) {
  const [title, setTitle] = useState(() => generatePrettyDefaultTitle(t));
  const [location, setLocation] = useState("");
  const [recordingMode, setRecordingMode] = useState<RecordingMode>("single_device");
  const [members, setMembers] = useState<WorkspaceMemberInfo[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [voiceRegisteredNames, setVoiceRegisteredNames] = useState<Set<string>>(new Set());

  // 카테고리 상태 - 폴더 안(lockedCategory)이면 고정, 아니면 최근 사용/기본값을 프리셋
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>(
    lockedCategory?.id ?? suggestedCategoryId ?? ""
  );
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");

  // 드롭다운 및 검색 상태
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const res = await getWorkspaceMembersApi(workspaceId);
      if (!cancelled && res.status === "success") {
        setMembers(res.members);
        // 회의를 시작하는 사람 본인은 참석자로 기본 선택해둔다 - 매번 스스로를 직접
        // 체크해줘야 하는 게 불편했던 부분.
        if (res.members.some((m) => m.user_id === currentUserId)) {
          setSelectedIds((prev) => new Set(prev).add(currentUserId));
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, currentUserId]);

  // 목소리 등록된 사람 표시용 - STT 서버에 등록된 화자 이름 전체 목록을 받아서,
  // 워크스페이스 멤버 이름과 매칭되는 사람 옆에 마이크 아이콘을 붙여준다.
  useEffect(() => {
    let cancelled = false;
    async function loadVoiceNames() {
      const res = await getVoiceProfileListApi();
      if (!cancelled && res.status === "success") {
        setVoiceRegisteredNames(new Set(res.names.map((n) => n.trim())));
      }
    }
    loadVoiceNames();
    return () => {
      cancelled = true;
    };
  }, []);

  function isVoiceRegistered(member: WorkspaceMemberInfo): boolean {
    const name = (member.display_name || member.username).trim();
    return voiceRegisteredNames.has(name);
  }

  function toggleMember(userId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }

  function removeMember(userId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(userId);
      return next;
    });
  }

  function handleSubmit() {
    if (!title.trim()) return;
    onStart(
      title.trim(),
      Array.from(selectedIds),
      location.trim() || undefined,
      recordingMode,
      selectedCategoryId || undefined
    );
  }

  async function handleCategorySelectChange(value: string) {
    if (value === CREATE_CATEGORY_VALUE) {
      setIsCreatingCategory(true);
      return;
    }
    setSelectedCategoryId(value);
  }

  function categoryLabel(category: Category): string {
    return category.is_default ? t.meeting_category_default_label : category.name;
  }

  async function handleConfirmCreateCategory() {
    const name = newCategoryName.trim();
    if (!name || !onCreateCategory) return;
    const created = await onCreateCategory(name);
    if (created) {
      setSelectedCategoryId(created.id);
    }
    setIsCreatingCategory(false);
    setNewCategoryName("");
  }

  // 새 카테고리 입력창이 열려 있을 때 바깥을 클릭하면 만들지 않고 드롭다운으로 되돌린다
  const categoryCreateRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isCreatingCategory) return;
    function handleClickOutside(e: MouseEvent) {
      if (categoryCreateRef.current && !categoryCreateRef.current.contains(e.target as Node)) {
        setIsCreatingCategory(false);
        setNewCategoryName("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isCreatingCategory]);

  // 검색어 필터링
  const filteredMembers = (members ?? []).filter((m) => {
    const name = m.display_name || m.username;
    return name.toLowerCase().includes(searchQuery.trim().toLowerCase());
  });

  const selectedMemberList = (members ?? []).filter((m) => selectedIds.has(m.user_id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex w-full max-w-md max-h-[90vh] flex-col rounded-2xl border border-recall-border bg-recall-bg shadow-2xl text-recall-text transition-all duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 - 스크롤 영역 밖에 고정 */}
        <div className="flex flex-shrink-0 items-center justify-between border-b border-recall-border px-6 pt-6 pb-3">
          <p className="text-lg font-bold text-recall-text">{t.meeting_start_modal_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text transition">
            <CloseIcon size={18} />
          </button>
        </div>

        {/* 본문 - 내용이 길어져도(카테고리, 팀원 드롭다운 등) 이 영역만 스크롤되고
            시작/취소 버튼은 항상 하단에 보인다 */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">

        {/* 1. 회의 제목 입력 */}
        <div className="mb-5">
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
            {t.meeting_title_field_label} <span className="text-recall-danger">*</span>
          </label>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder={t.meeting_title_input_placeholder}
            className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text font-medium outline-none focus:border-recall-accent transition"
          />
        </div>

        {/* 1-1. 회의 장소 입력 (선택 항목이라 마커 없음, 필수 항목만 * 표시) */}
        <div className="mb-5">
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
            {t.meeting_minutes_location_label}
          </label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder={t.meeting_location_placeholder}
            className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text font-medium outline-none focus:border-recall-accent transition"
          />
        </div>

        {/* 1-2. 녹음 방식 선택 */}
        <div className="mb-5">
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
            {t.meeting_recording_mode_label}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setRecordingMode("single_device")}
              className={`rounded-xl border px-3 py-2.5 text-left transition ${
                recordingMode === "single_device"
                  ? "border-recall-accent bg-recall-accent/10"
                  : "border-recall-border hover:bg-white/5"
              }`}
            >
              <p className="text-sm font-semibold text-recall-text">{t.meeting_mode_single_title}</p>
              <p className="mt-0.5 text-[11px] text-recall-textMuted leading-relaxed">
                {t.meeting_mode_single_desc}
              </p>
            </button>
            <button
              type="button"
              onClick={() => setRecordingMode("individual")}
              className={`rounded-xl border px-3 py-2.5 text-left transition ${
                recordingMode === "individual"
                  ? "border-recall-accent bg-recall-accent/10"
                  : "border-recall-border hover:bg-white/5"
              }`}
            >
              <p className="text-sm font-semibold text-recall-text">{t.meeting_mode_individual_title}</p>
              <p className="mt-0.5 text-[11px] text-recall-textMuted leading-relaxed">
                {t.meeting_mode_individual_desc}
              </p>
            </button>
          </div>

          {recordingMode === "single_device" && (
            <p className="mt-2 rounded-lg bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-recall-textMuted">
              {t.meeting_voice_hint_prefix} <span className="font-medium text-recall-text">{t.meeting_voice_hint_bold}</span>
              {t.meeting_voice_hint_suffix}
            </p>
          )}
        </div>

        {/* 1-3. 카테고리 선택 - 카테고리 API가 아직 없으면(categories가 비어 있으면) 통째로 숨긴다 */}
        {(lockedCategory || categories.length > 0) && (
          <div className="mb-5">
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
              {t.meeting_category_label}
            </label>

            {lockedCategory ? (
              <div className="flex items-center gap-2 rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm font-medium text-recall-text">
                <span>{categoryLabel(lockedCategory)}</span>
              </div>
            ) : isCreatingCategory ? (
              <div ref={categoryCreateRef} className="flex gap-2">
                <input
                  autoFocus
                  value={newCategoryName}
                  onChange={(e) => setNewCategoryName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleConfirmCreateCategory();
                    if (e.key === "Escape") setIsCreatingCategory(false);
                  }}
                  placeholder={t.meeting_category_create_placeholder}
                  className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text font-medium outline-none focus:border-recall-accent transition"
                />
                <button
                  type="button"
                  onClick={handleConfirmCreateCategory}
                  disabled={!newCategoryName.trim()}
                  className="whitespace-nowrap rounded-xl bg-recall-accent px-3.5 py-2.5 text-sm font-semibold text-white disabled:opacity-50 transition"
                >
                  {t.meeting_category_create_confirm}
                </button>
              </div>
            ) : (
              <select
                value={selectedCategoryId}
                onChange={(e) => handleCategorySelectChange(e.target.value)}
                className="w-full rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text font-medium outline-none focus:border-recall-accent transition"
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {categoryLabel(c)}
                    {c.id === suggestedCategoryId ? ` (${t.meeting_category_label})` : ""}
                  </option>
                ))}
                {onCreateCategory && <option value={CREATE_CATEGORY_VALUE}>{t.meeting_category_create_option}</option>}
              </select>
            )}

            <p className="mt-1.5 text-[11px] text-recall-textMuted">
              {lockedCategory ? t.meeting_category_locked_hint : t.meeting_category_default_hint}
            </p>
          </div>
        )}

        {/* 2. 팀원 선택 영역 (아코디언 방식 - 버튼들을 아래로 밀어냄) */}
        <div className="mb-5">
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-recall-textMuted">
            {t.meeting_select_attendees_label}
          </label>

          <button
            type="button"
            onClick={() => setIsDropdownOpen((prev) => !prev)}
            className="flex w-full items-center justify-between rounded-xl border border-recall-border bg-recall-bgSoft px-3.5 py-2.5 text-sm text-recall-text hover:border-recall-accent/60 transition"
          >
            <span className="text-recall-textMuted">{t.meeting_select_attendees_placeholder}</span>
            <ChevronDownIcon size={16} className={`text-recall-textMuted transition-transform ${isDropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {/* 인라인 열림 방식 (버튼을 가리지 않고 아래로 밀어냄) */}
          {isDropdownOpen && (
            <div className="mt-2 flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft overflow-hidden transition-all">
              {/* 팀원 검색 입력창 */}
              <div className="p-2 border-b border-recall-border">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t.meeting_search_members_placeholder}
                  className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
                />
              </div>

              {/* 약 2명 높이(max-h-24)로 제한하여 콤팩트하게 스크롤 제공 */}
              <div className="max-h-24 overflow-y-auto p-1.5 space-y-0.5">
                {members === null ? (
                  <p className="p-2 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
                ) : filteredMembers.length === 0 ? (
                  <p className="p-2 text-center text-xs text-recall-textMuted">
                    {searchQuery ? t.meeting_no_search_results : t.meeting_no_selectable_members}
                  </p>
                ) : (
                  filteredMembers.map((m) => {
                    const isSelected = selectedIds.has(m.user_id);
                    const name = m.display_name || m.username;
                    return (
                      <button
                        key={m.user_id}
                        type="button"
                        onClick={() => toggleMember(m.user_id)}
                        className="flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-sm hover:bg-white/5 transition"
                      >
                        <span className="flex items-center gap-1.5 font-medium text-recall-text">
                          {name}
                          {isVoiceRegistered(m) && (
                            <MicIcon size={12} className="flex-shrink-0 text-recall-accent" />
                          )}
                        </span>
                        {isSelected && (
                          <CheckIcon size={16} className="text-recall-accent flex-shrink-0" />
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* 3. 선택된 팀원 칩(Badge) 영역 */}
          {selectedMemberList.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">
              {selectedMemberList.map((m) => {
                const name = m.display_name || m.username;
                return (
                  <span
                    key={m.user_id}
                    className="inline-flex items-center gap-1.5 rounded-full border border-recall-border bg-recall-accent/10 px-2.5 py-1 text-xs font-medium text-recall-text"
                  >
                    <span>{name}</span>
                    {isVoiceRegistered(m) && (
                      <span title={t.meeting_voice_registered_tooltip}>
                        <MicIcon size={11} className="flex-shrink-0 text-recall-accent" />
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeMember(m.user_id)}
                      className="text-recall-textMuted hover:text-recall-danger transition"
                      title={t.meeting_remove_chip}
                    >
                      <CloseIcon size={12} />
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>

        </div>

        {/* 하단 버튼 - 스크롤 영역 밖에 고정되어 항상 보임 */}
        <div className="flex flex-shrink-0 justify-end gap-2 border-t border-recall-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition"
          >
            {t.task_cancel}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!title.trim()}
            className="rounded-xl bg-recall-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition shadow-md shadow-recall-accent/20"
          >
            {t.meeting_start_btn}
          </button>
        </div>
      </div>
    </div>
  );
}