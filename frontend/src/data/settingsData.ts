export const SETTINGS_TABS = ['프로필', '계정', '알림', '보안', '팀 관리'] as const

export type SettingsTab = (typeof SETTINGS_TABS)[number]

export const NOTIFICATION_ITEMS = [
  { id: 'analysis', label: '회의 분석 완료 알림', desc: '분석이 완료되면 알림을 받아요' },
  { id: 'deadline', label: '업무 마감 알림', desc: '업무 마감 1일 전에 알림을 받아요' },
  { id: 'email_draft', label: '이메일 초안 생성 알림', desc: '이메일 초안이 생성되면 알림을 받아요' },
  { id: 'team_done', label: '팀원 업무 완료 알림', desc: '팀원이 업무를 완료하면 알림을 받아요' },
] as const

export type NotificationId = (typeof NOTIFICATION_ITEMS)[number]['id']