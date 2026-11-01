/** 批次2 refs git 链：导出响应的 commit 字段 → 提示语尾巴。
 * commit 有值 = 已 commit+push 本地 Gitea（refsadmin/eia-refs，短码 8 位）；
 * null = REFS_REPO_WORKTREE 未配置（git 链未启用，仅落技能文件）。 */
export function refsCommitNote(commit) {
  return commit
    ? `已提交本地 git（commit ${String(commit).slice(0, 8)}）`
    : '已写回技能文件（refs git 链未启用）'
}
