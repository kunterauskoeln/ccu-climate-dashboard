import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "./theme/ThemeContext";
import TransferBanner from "./components/TransferBanner";
import DewPointBanner from "./components/DewPointBanner";
import DeviceHealthBanner from "./components/DeviceHealthBanner";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000, // most of this data changes on the CCU's own schedule, not per-render
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

const RoomOverview = lazy(() => import("./components/RoomOverview"));
const RoomDetail = lazy(() => import("./components/RoomDetail"));
const Settings = lazy(() => import("./components/Settings"));
const Devices = lazy(() => import("./components/Devices"));
const HeatingProfiles = lazy(() => import("./components/HeatingProfiles"));
const HeatingProfileDetail = lazy(() => import("./components/HeatingProfileDetail"));
const HeatingProfileDayDetail = lazy(() => import("./components/HeatingProfileDayDetail"));
const DeviceDetail = lazy(() => import("./components/DeviceDetail"));
const TimeBlockDetail = lazy(() => import("./components/TimeBlockDetail"));
const TimeBlockAdd = lazy(() => import("./components/TimeBlockAdd"));
const ThemeSettings = lazy(() => import("./components/ThemeSettings"));
const ChangeHistory = lazy(() => import("./components/ChangeHistory"));
const Backup = lazy(() => import("./components/Backup"));
const DewPoint = lazy(() => import("./components/DewPoint"));
const Absence = lazy(() => import("./components/Absence"));
const ValveHistory = lazy(() => import("./components/ValveHistory"));

function LoadingFallback() {
  return <div className="loading" style={{ padding: "2rem", textAlign: "center" }}>Lade...</div>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <DewPointBanner />
          <DeviceHealthBanner />
          <TransferBanner />
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/" element={<RoomOverview />} />
              <Route path="/room/:roomName" element={<RoomDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/settings/theme" element={<ThemeSettings />} />
              <Route path="/settings/history" element={<ChangeHistory />} />
              <Route path="/settings/backup" element={<Backup />} />
              <Route path="/settings/dew-point" element={<DewPoint />} />
              <Route path="/settings/absence" element={<Absence />} />
              <Route path="/settings/valves" element={<ValveHistory />} />
              <Route path="/settings/devices" element={<Devices />} />
              <Route path="/settings/devices/:deviceId" element={<DeviceDetail />} />
              <Route path="/settings/heating-profiles" element={<HeatingProfiles />} />
              <Route path="/settings/heating-profiles/:roomName/:profileName" element={<HeatingProfileDetail />} />
              <Route path="/settings/heating-profiles/:roomName/:profileName/:day" element={<HeatingProfileDayDetail />} />
              <Route path="/settings/heating-profiles/:roomName/:profileName/:day/:blockIndex" element={<TimeBlockDetail />} />
              <Route path="/settings/heating-profiles/:roomName/:profileName/:day/add" element={<TimeBlockAdd />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
