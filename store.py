"""
增量状态存储。

职责：记住「每个 UP 主已经见过的作品 id」，从而回答「这条是不是新的」。
只用 JSON 落盘（state/seen.json），无数据库依赖，方便人工查看与回滚。

设计要点：
  · 每个来源（platform:uid）保存最近 N 条 id（默认 200），足够覆盖长期未跑
    导致的一次性大批量补推，又不会无限膨胀。
  · 首次见到某个来源时，把当前列表**全部记为已见**（不推送历史存量），
    除非配置里显式打开 notify_on_first_run。
"""
import json
import time
from pathlib import Path
from typing import Optional

from core.config import STATE_DIR

MAX_SEEN = 200
SCHEMA = 1


class SeenStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else STATE_DIR / 'seen.json'
        self._data = {'schema': SCHEMA, 'sources': {}}
        self.load()

    # ---------------------------------------------------------------- 读写
    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('sources'), dict):
                self._data = data
        except Exception:
            # 状态文件损坏时不静默重置：备份后从空起步
            try:
                self.path.rename(self.path.with_suffix('.corrupt.json'))
            except Exception:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                       encoding='utf-8')
        tmp.replace(self.path)

    # ---------------------------------------------------------------- 访问
    @staticmethod
    def key(platform: str, ident: str) -> str:
        return f'{platform}:{ident}'

    def entry(self, platform: str, ident: str) -> dict:
        return self._data['sources'].setdefault(
            self.key(platform, ident),
            {'seen': [], 'meta': {}, 'checked_at': '', 'first_seen_at': ''},
        )

    def known(self, platform: str, ident: str) -> bool:
        """该来源是否已有基线（决定是否走「首次静默建基线」）。"""
        return bool(self._data['sources'].get(self.key(platform, ident), {}).get('first_seen_at'))

    def is_new(self, platform: str, ident: str, vid: str) -> bool:
        return vid not in self.entry(platform, ident)['seen']

    def mark(self, platform: str, ident: str, vids: list, meta: dict = None) -> None:
        """把一批作品 id 记为已见（新的排前面，去重，截断到 MAX_SEEN）。"""
        e = self.entry(platform, ident)
        merged = list(dict.fromkeys([v for v in vids if v] + e['seen']))
        e['seen'] = merged[:MAX_SEEN]
        e['checked_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        if not e['first_seen_at']:
            e['first_seen_at'] = e['checked_at']
        if meta:
            e['meta'] = meta

    def stats(self) -> str:
        lines = []
        for k, v in sorted(self._data['sources'].items()):
            lines.append(f"  {k:32} 已见 {len(v.get('seen', [])):>3} 条 "
                         f"最后检查 {v.get('checked_at') or '—'}")
        return '\n'.join(lines) or '  （暂无记录）'
