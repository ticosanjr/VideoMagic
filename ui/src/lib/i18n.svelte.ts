import { t } from "./i18n";

let current = $state("en");

export const i18n = {
  get locale(): string {
    return current;
  },
  set(value: string): void {
    current = value;
  },
  t(key: string): string {
    return t(current, key);
  }
};
