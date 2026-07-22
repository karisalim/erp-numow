import React from 'react';
import { Routes, Route } from 'react-router-dom';
import {
  RecipeDashboardPage, RecipeDetailPage, RecipeEditorPage,
  RecipeVersionsPage, ModifiersPage, RecipeReportsPage,
} from '../pages';

/**
 * The Recipe app's own routing tree, mounted into the main app as a single
 * `/recipes/*` route (see `App.tsx`) — this is the ONE integration point;
 * nothing outside this file needs to know the app's internal page/route
 * structure, so it can keep evolving without touching POS/Inventory/Sales
 * routing.
 *
 * Route order matters: `/new` must be listed before `/:id` so "new" isn't
 * swallowed as a product id param.
 */
export const RecipesApp: React.FC = () => (
  <Routes>
    <Route index element={<RecipeDashboardPage />} />
    <Route path="new" element={<RecipeEditorPage />} />
    <Route path="modifiers" element={<ModifiersPage />} />
    <Route path="reports" element={<RecipeReportsPage />} />
    <Route path=":id" element={<RecipeDetailPage />} />
    <Route path=":id/edit" element={<RecipeEditorPage />} />
    <Route path=":id/versions" element={<RecipeVersionsPage />} />
  </Routes>
);
