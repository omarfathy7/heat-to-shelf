from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData, RouteSegment
from app.infrastructure.database.geo import coords_from, line_wkt
from app.infrastructure.database.models import Route as RouteORM
from app.infrastructure.database.models import RouteSegment as RouteSegmentORM


class RouteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, shipment_id: UUID, route: RouteData, segments: list[RouteSegment]) -> tuple[RouteORM, list[RouteSegmentORM]]:
        coords = [c.as_tuple() for c in route.geometry]
        route_row = RouteORM(
            shipment_id=shipment_id,
            provider=route.provider,
            provider_route_id=route.provider_route_id,
            geometry=line_wkt(coords),
            distance_meters=route.distance_meters,
            duration_seconds=route.duration_seconds,
            route_points=[{"longitude": p[0], "latitude": p[1]} for p in coords],
            raw_response_ref=route.raw_response_ref,
        )
        self.session.add(route_row)
        self.session.flush()

        segment_rows: list[RouteSegmentORM] = []
        for segment in segments:
            seg = RouteSegmentORM(
                route_id=route_row.id,
                sequence=segment.sequence,
                geometry=line_wkt([c.as_tuple() for c in segment.geometry]),
                start_distance_meters=segment.start_distance_meters,
                end_distance_meters=segment.end_distance_meters,
                estimated_arrival_utc=segment.estimated_arrival_utc,
                duration_seconds=segment.duration_seconds,
            )
            self.session.add(seg)
            segment_rows.append(seg)
        self.session.flush()
        return route_row, segment_rows

    def get_for_shipment(self, shipment_id: UUID) -> RouteORM | None:
        return self.session.execute(
            select(RouteORM).where(RouteORM.shipment_id == shipment_id).limit(1)
        ).scalar_one_or_none()

    def get_segments_for_route(self, route_id: UUID) -> list[RouteSegmentORM]:
        return (
            self.session.execute(
                select(RouteSegmentORM)
                .where(RouteSegmentORM.route_id == route_id)
                .order_by(RouteSegmentORM.sequence)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def route_to_domain(row: RouteORM) -> RouteData:
        return RouteData(
            provider=row.provider,
            provider_route_id=row.provider_route_id,
            geometry=[
                Coordinate(longitude=p[0], latitude=p[1])
                for p in coords_from(row.geometry)
            ],
            distance_meters=row.distance_meters,
            duration_seconds=row.duration_seconds,
            raw_response_ref=row.raw_response_ref,
            metadata={"route_points": row.route_points},
        )