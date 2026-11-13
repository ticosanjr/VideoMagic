import {
  createNotice,
  noticeAllowed,
  type Notice,
  type NoticeInput,
  type NoticeLevel
} from "./notifications";

let items = $state<Notice[]>([]);
const MAX_NOTICES = 50;
let level = $state<NoticeLevel>("off");



export const notifications = {
  get items(): Notice[] {
    return items;
  },
  get level(): NoticeLevel {
    return level;
  },
  setLevel(value: NoticeLevel): void {
    level = value;
  },
  push(input: NoticeInput): Notice {
    const notice = createNotice(input);
    if (noticeAllowed(level, input)) {
      items = [notice, ...items].slice(0, MAX_NOTICES);
    }
    return notice;
  },
  dismiss(id: string): void {
    items = items.filter((notice) => notice.id !== id);
  },
  clear(): void {
    items = [];
  }
};
