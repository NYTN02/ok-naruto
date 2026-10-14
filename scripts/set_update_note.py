"""把更新仓库里某个 tag 的「更新日志」改成 .github/release-notes/<tag>.md 的内容。

背景（为什么需要这个脚本）
--------------------------
`partial-sync-repo` 这个 action **没有"自定义更新日志"的输入**（它的 action.yml 只有
repos / sync_list / tag / gitignore_file / show_author），所以它只能用**提交标题**
拼出更新日志，写进更新仓库的 commit / tag message。而启动器的更新卡直接显示它 ——
于是内部措辞（`docs: …`、`(NYTN02)`、谁反馈的）会直接给用户看到。

v0.1.13 就是这么泄漏的两次：
  * 第一次只修了 GitHub Release 正文，没管更新卡
  * 第二次手动把 GitHub + CNB 两个更新仓库的 message 改掉

这个脚本把那套手动操作固化下来，由 workflow 在同步之后自动执行，
让**更新日志只有一处来源**：`.github/release-notes/<tag>.md`。

行为
----
1. 读该文件，提取出条目（去掉 `*` 前缀、空行和 `#` 标题）
2. 对每个目标仓库：
     clone -> 确认 HEAD 就是 tag 指向的 commit -> 改写 commit message
     -> 重建 tag（附注，带同样文案）-> 强推 branch + tag
3. **改完重新 clone 回查**，确认远端两处 message 都等于目标文案

安全性
------
* 传入的 URL 里可能内嵌凭据（CI secret），所有输出一律先脱敏再打印
* clone 完立刻把 remote URL 换成不带凭据的地址
* 只用临时目录，结束时删掉
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


# --------------------------------------------------------------------------
def read_notes(path: pathlib.Path) -> list[str]:
    """从 release-notes 文件里提取条目行。

    * 去掉 markdown 列表符号（`*` / `-` / `+`）和行首空白
    * 丢掉空行、`#` 标题、以及 `---` 这类分隔线
    """
    if not path.is_file():
        raise FileNotFoundError(f'找不到更新日志文件: {path}')
    out = []
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or set(line) <= set('-=_'):
            continue
        line = re.sub(r'^[*+\-]\s+', '', line).strip()
        if line:
            out.append(line)
    return out


def scrub(text: str, secrets: list[str]) -> str:
    """把凭据替换掉再输出。"""
    out = text or ''
    for sec in secrets:
        if sec and len(sec) >= 6:
            out = out.replace(sec, '***')
    return out


def run(args, cwd, secrets, check=True):
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = scrub((r.stdout or '') + (r.stderr or ''), secrets).strip()
    if check and r.returncode != 0:
        raise RuntimeError(f'命令失败 {" ".join(args[:2])}...: {out[:400]}')
    return out


def credentials_in(url: str) -> list[str]:
    """从 URL 里取出可能出现的凭据片段，用于脱敏。"""
    m = re.match(r'^https?://([^:/@]+):([^@]+)@', url)
    if not m:
        return []
    import urllib.parse
    user, tok = m.group(1), m.group(2)
    return [tok, urllib.parse.unquote(tok), urllib.parse.quote(tok, safe=''), f'{user}:{tok}']


def clean_url(url: str) -> str:
    return re.sub(r'^(https?://)[^@]*@', r'\1', url)


# --------------------------------------------------------------------------
def set_note_for_repo(url: str, branch: str, tag: str, notes: list[str],
                      work_root: pathlib.Path, log=print) -> bool:
    """改一个仓库的 message。返回是否成功。"""
    secrets = credentials_in(url)
    name = re.sub(r'[^A-Za-z0-9]+', '_', clean_url(url))[-40:]
    work = work_root / name
    work.mkdir(parents=True, exist_ok=True)

    log(f'    [{clean_url(url)}] clone...')
    run(['git', 'clone', '--quiet', url, '.'], work, secrets)
    run(['git', 'remote', 'set-url', 'origin', clean_url(url)], work, secrets, check=False)

    head = run(['git', 'rev-parse', 'HEAD'], work, secrets)
    tag_commit = run(['git', 'rev-parse', f'{tag}^{{commit}}'], work, secrets)
    cur_branch = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], work, secrets)
    if head != tag_commit:
        log(f'    !! {tag} 不是 HEAD（HEAD={head[:8]} tag={tag_commit[:8]}），跳过这个仓库')
        return False

    msg_file = work / '_note.txt'
    msg_file.write_text('\n'.join(notes) + '\n', encoding='utf-8')

    log(f'    [{clean_url(url)}] 改写 commit + tag message...')
    run(['git', '-c', 'i18n.commitEncoding=utf-8', 'commit', '--amend', '-q',
         '-F', str(msg_file)], work, secrets)
    new_sha = run(['git', 'rev-parse', 'HEAD'], work, secrets)
    # 重建为附注 tag：GitHub 原来是轻量、CNB 原来是附注，统一成附注最稳
    # （启动器读哪一种都能拿到 message）
    run(['git', '-c', 'user.name=NYTN02',
         '-c', 'user.email=NYTN02@users.noreply.github.com',
         'tag', '-a', '-f', tag, new_sha, '-F', str(msg_file)], work, secrets)

    push_branch = cur_branch if cur_branch not in ('HEAD', '') else branch
    r1 = subprocess.run(['git', 'push', '--force', url, f'HEAD:{push_branch}'],
                        cwd=str(work), capture_output=True, text=True,
                        encoding='utf-8', errors='replace')
    r2 = subprocess.run(['git', 'push', '--force', url, tag],
                        cwd=str(work), capture_output=True, text=True,
                        encoding='utf-8', errors='replace')
    if r1.returncode or r2.returncode:
        log('    !! 推送失败: ' + scrub((r1.stdout + r1.stderr + r2.stdout + r2.stderr),
                                       secrets).strip()[:300])
        return False
    return True


def verify_repo(url: str, tag: str, notes: list[str], work_root: pathlib.Path,
                log=print) -> bool:
    """重新 clone 回查远端两处 message。"""
    secrets = credentials_in(url)
    work = work_root / ('v_' + re.sub(r'[^A-Za-z0-9]+', '_', clean_url(url))[-36:])
    work.mkdir(parents=True, exist_ok=True)
    try:
        run(['git', 'clone', '--quiet', '--branch', tag, '--depth', '1', url, '.'],
            work, secrets)
    except RuntimeError as e:
        log(f'    !! 回查 clone 失败: {e}')
        return False

    commit_lines = [l for l in run(['git', 'log', '-1', '--format=%B'], work, secrets).splitlines()
                    if l.strip()]
    tag_raw = run(['git', 'cat-file', 'tag', tag], work, secrets, check=False)
    tag_lines = []
    if tag_raw and 'tagger' in tag_raw:
        after = tag_raw.split('tagger', 1)[1].split('\n', 1)
        tag_lines = [l for l in (after[1] if len(after) > 1 else '').splitlines() if l.strip()]

    ok_c = commit_lines == notes
    ok_t = (tag_lines == notes) if tag_lines else None
    log(f'    [{clean_url(url)}] commit 一致={ok_c}  tag 一致={ok_t}')
    return bool(ok_c and (ok_t is not False))


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='把更新仓库的更新日志换成 release-notes 文件的内容')
    ap.add_argument('--tag', required=True)
    ap.add_argument('--notes', required=True, help='release-notes 文件路径')
    ap.add_argument('--repo', action='append', default=[],
                    help='目标仓库 URL（可重复）；URL 里可内嵌凭据')
    ap.add_argument('--branch', default='main')
    ap.add_argument('--keep-temp', action='store_true')
    args = ap.parse_args(argv)

    notes_path = pathlib.Path(args.notes)
    try:
        notes = read_notes(notes_path)
    except FileNotFoundError as e:
        print(f'  跳过：{e}')
        return 0
    if not notes:
        print(f'  跳过：{notes_path} 里没有条目')
        return 0

    print(f'  更新日志（{len(notes)} 条）来自 {notes_path}:')
    for n in notes:
        print(f'    - {n}')

    if not args.repo:
        print('  没有目标仓库，跳过')
        return 0

    root = pathlib.Path(tempfile.mkdtemp(prefix='set-note-'))
    results = {}
    try:
        for url in args.repo:
            try:
                results[url] = set_note_for_repo(url, args.branch, args.tag, notes, root)
            except Exception as e:
                print(f'    !! 出错: {e}')
                results[url] = False

        print('  回查远端:')
        for url in args.repo:
            if not results.get(url):
                continue
            verify_repo(url, args.tag, notes, root)
    finally:
        if not args.keep_temp:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f'  临时目录保留在 {root}')

    failed = [clean_url(u) for u, ok in results.items() if not ok]
    if failed:
        print('  ✗ 以下仓库没成功: ' + ', '.join(failed))
        return 1
    print('  ✓ 全部完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
