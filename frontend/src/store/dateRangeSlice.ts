import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface CustomDateRange {
  start: string;
  end: string;
}

export interface DateRangeState {
  selectedDays: number | undefined;
  appliedCustom: CustomDateRange | null;
}

const initialState: DateRangeState = {
  selectedDays: undefined,
  appliedCustom: null,
};

const dateRangeSlice = createSlice({
  name: 'dateRange',
  initialState,
  reducers: {
    setDatePreset(state, action: PayloadAction<number | undefined>) {
      state.appliedCustom = null;
      state.selectedDays = action.payload;
    },
    setCustomDateRange(state, action: PayloadAction<CustomDateRange | null>) {
      if (action.payload && (action.payload.start || action.payload.end)) {
        state.selectedDays = undefined;
        state.appliedCustom = action.payload;
      } else {
        state.appliedCustom = null;
        state.selectedDays = undefined;
      }
    },
  },
});

export const { setDatePreset, setCustomDateRange } = dateRangeSlice.actions;

export function buildDateRangeQueryParams(
  selectedDays: number | undefined,
  appliedCustom: CustomDateRange | null,
): { days?: number; start_date?: string; end_date?: string } | undefined {
  if (appliedCustom?.start || appliedCustom?.end) {
    return {
      start_date: appliedCustom.start || undefined,
      end_date: appliedCustom.end || undefined,
    };
  }
  return selectedDays ? { days: selectedDays } : undefined;
}

export function isIsoDateInRange(
  isoDate: string | null | undefined,
  selectedDays: number | undefined,
  appliedCustom: CustomDateRange | null,
): boolean {
  if (!isoDate) return true;
  const ts = Date.parse(isoDate);
  if (Number.isNaN(ts)) return true;
  if (appliedCustom?.start || appliedCustom?.end) {
    if (appliedCustom.start) {
      const startTs = Date.parse(`${appliedCustom.start}T00:00:00Z`);
      if (!Number.isNaN(startTs) && ts < startTs) return false;
    }
    if (appliedCustom.end) {
      const endTs = Date.parse(`${appliedCustom.end}T23:59:59Z`);
      if (!Number.isNaN(endTs) && ts > endTs) return false;
    }
    return true;
  }
  if (selectedDays) {
    const cutoff = Date.now() - selectedDays * 24 * 60 * 60 * 1000;
    return ts >= cutoff;
  }
  return true;
}

export default dateRangeSlice.reducer;
