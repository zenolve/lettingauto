import { Navigate, Route, Routes } from "react-router-dom";

import { AgentLayout } from "./components/layout/AgentLayout";
import { PublicLayout } from "./components/layout/PublicLayout";
import { RequireAuth } from "./components/RequireAuth";
import ContractEditorPage from "./pages/ContractEditorPage";
import Dashboard from "./pages/Dashboard";
import LandlordAdmin from "./pages/forms/LandlordAdmin";
import LandlordVerification from "./pages/forms/LandlordVerification";
import MoveIn from "./pages/forms/MoveIn";
import Offer from "./pages/forms/Offer";
import PropertyTakeon from "./pages/forms/PropertyTakeon";
import LibraryEditor from "./pages/LibraryEditor";
import LibraryIndex from "./pages/LibraryIndex";
import Login from "./pages/Login";
import Properties from "./pages/Properties";
import PropertyDetail from "./pages/PropertyDetail";
import PropertyUploads from "./pages/PropertyUploads";
import Signatures from "./pages/Signatures";
import TemplateEditor from "./pages/TemplateEditor";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Public landlord/tenant form pages — gated by URL token, no agent login */}
      <Route element={<PublicLayout />}>
        <Route path="/landlord/admin" element={<LandlordAdmin />} />
        <Route path="/landlord/verify" element={<LandlordVerification />} />
      </Route>

      {/* Agent app */}
      <Route element={<RequireAuth><AgentLayout /></RequireAuth>}>
        <Route path="/agent" element={<Dashboard />} />
        <Route path="/agent/properties" element={<Properties />} />
        <Route path="/agent/signatures" element={<Signatures />} />
        <Route path="/agent/library" element={<LibraryIndex />} />
        <Route path="/agent/library/:docId" element={<TemplateEditor />} />
        <Route path="/agent/properties/new" element={<PropertyTakeon />} />
        <Route path="/agent/properties/:id" element={<PropertyDetail />} />
        <Route path="/agent/properties/:id/uploads" element={<PropertyUploads />} />
        <Route path="/agent/properties/:id/offer" element={<Offer />} />
        <Route path="/agent/properties/:id/move-in" element={<MoveIn />} />
        <Route path="/agent/properties/:id/contracts/:template" element={<ContractEditorPage />} />
        <Route path="/agent/properties/:id/library/:docId" element={<LibraryEditor />} />
      </Route>

      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  );
}
