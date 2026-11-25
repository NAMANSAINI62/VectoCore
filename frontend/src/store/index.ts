import { configureStore } from '@reduxjs/toolkit';
import { setupListeners } from '@reduxjs/toolkit/query';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import { cacheApi } from './cacheApi';
import dateRangeReducer from './dateRangeSlice';

export const store = configureStore({
  reducer: {
    [cacheApi.reducerPath]: cacheApi.reducer,
    dateRange: dateRangeReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(cacheApi.middleware),
});

setupListeners(store.dispatch);

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
