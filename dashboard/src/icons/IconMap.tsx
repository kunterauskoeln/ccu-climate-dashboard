import React from "react";
import { Icon } from "@iconify/react";

export const ICONS = {
  "hm-rcv-50": <Icon icon="mdi:gesture-tap" width="28" />,
  "hmip-rcv-50": <Icon icon="mdi:gesture-tap" width="28" />,
  "hmip-ccu3": <Icon icon="mdi:home-automation" width="28" />,
  "hmip-falmot-c12": <Icon icon="mdi:valve" width="28" />,
  "hmip-wth-1": <Icon icon="mdi:thermostat" width="28" />,
  abwesenheit: <Icon icon="mdi:bag-suitcase-outline" width="28" />,
  ankleide: <Icon icon="mdi:hanger" width="28" />,
  arbeitszimmer: <Icon icon="mdi:desk" width="28" />,
  arrowleft: <Icon icon="mdi:arrow-left-thin" width="28" />,
  back: <Icon icon="mdi:arrow-left-thin" width="28" />,
  backup: <Icon icon="mdi:database-export-outline" width="28" />,
  import: <Icon icon="mdi:database-import-outline" width="28" />,
  bad: <Icon icon="mdi:shower" width="28" />,
  check: <Icon icon="mdi:check" width="28" />,
  "chevron-up": <Icon icon="mdi:chevron-up" width="28" />,
  devices: <Icon icon="mdi:thermostat-box" width="28" />,
  flur: <Icon icon="mdi:door" width="28" />,
  history: <Icon icon="mdi:history" width="28" />,
  küche: <Icon icon="mdi:stove" width="28" />,
  profile: <Icon icon="mdi:calendar-clock-outline" width="28" />,
  schlafzimmer: <Icon icon="mdi:bed-king" width="28" />,
  taupunkt: <Icon icon="mdi:water-thermometer-outline" width="28" />,
  thermometer: <Icon icon="mdi:thermometer" width="28" />,
  themes: <Icon icon="mdi:palette-outline" width="28" />,
  tropfen: <Icon icon="mdi:water-outline" width="28" />,
  verlauf: <Icon icon="mdi:chart-line" width="28" />,
  wc: <Icon icon="mdi:human-male-female" width="28" />,
  wohnung: <Icon icon="mdi:home-outline" width="28" />,
  wohnzimmer: <Icon icon="mdi:sofa" width="28" />,
  zahnrad: <Icon icon="mdi:cog-outline" width="28" />,
  default: <Icon icon="mdi:help-box" width="28" />
} as const;

export type IconName = keyof typeof ICONS;

type IconElement = React.ReactElement<React.ComponentProps<typeof Icon>>;

const getIconElement = (name: string): IconElement => {
  const key = name?.toLowerCase();
  return (ICONS as Record<string, IconElement>)[key] || ICONS.default;
};

export const getIcon = (name: string): IconElement => getIconElement(name);

export function AppIcon({
  name,
  width = 28,
  className
}: {
  name: IconName | string;
  width?: number | string;
  className?: string;
}): IconElement {
  const icon = getIconElement(name);
  return React.cloneElement(icon, { width, className });
}
